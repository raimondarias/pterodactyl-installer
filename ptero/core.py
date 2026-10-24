#!/usr/bin/env python3
"""Instalador independiente de Pterodactyl 2 y Wings. Solo biblioteca estándar."""
import argparse
import contextlib
import datetime as dt
import fcntl
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import __version__

PANEL_VERSION = "v2.0.0-beta.2"
WINGS_VERSION = "v1.13.4"
PROJECT = "ptero-installer"
SCHEMA = 1


class InstallerError(Exception):
    pass


class Cancelled(InstallerError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InstallerError("La API redirige la petición. Introduce la URL final del Panel.")


def node_configuration(payload, url):
    """Mismos campos remotos permitidos por Wings PanelConfiguration, sin indirection."""
    try:
        if not isinstance(payload, dict):
            raise ValueError("objeto esperado")
        uuid.UUID(payload["uuid"])
        for field in ("token", "token_id"):
            value = payload[field]
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                raise ValueError("token no válido o con indirection")
        api = payload["api"]
        port = api["port"]
        sftp = payload["system"]["sftp"]["bind_port"]
        if any(type(value) is not int or not 1 <= value <= 65535 for value in (port, sftp)):
            raise ValueError("puerto no válido")
        host = api.get("host", "0.0.0.0")
        if not valid_host(host):
            raise ValueError("host de escucha no válido")
        ssl = api["ssl"]
        if type(ssl["enabled"]) is not bool:
            raise ValueError("ssl.enabled debe ser booleano")
        for field in ("cert", "key"):
            if not isinstance(ssl.get(field, ""), str):
                raise ValueError("ruta SSL no válida")
            if ssl["enabled"] and not Path(ssl.get(field, "")).is_absolute():
                raise ValueError("SSL necesita rutas absolutas de certificado y clave")
        upload = api.get("upload_limit", 100)
        if type(upload) is not int or upload < 0:
            raise ValueError("upload_limit no válido")
        return {"debug": False, "uuid": payload["uuid"], "token_id": payload["token_id"],
                "token": payload["token"], "api": {"host": host, "port": port,
                "ssl": {key: ssl.get(key, "") for key in ("enabled", "cert", "key")}, "upload_limit": upload},
                "system": {"sftp": {"bind_port": sftp}}, "remote": url}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InstallerError("La API no devolvió una configuración de nodo válida.") from exc


def atomic_write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise InstallerError(f"No se escribe sobre un enlace simbólico: {path}")
    fd, name = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, data):
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise InstallerError(f"No se puede leer JSON: {path}: {exc}") from exc


def valid_email(value):
    return bool(re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value))


def valid_host(value):
    if len(value) > 253 or not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
                   for part in value.split("."))


def valid_domain(value):
    try:
        ipaddress.ip_address(value)
        return False
    except ValueError:
        return valid_host(value) and "." in value


def valid_url(value):
    try:
        url = urllib.parse.urlsplit(value)
        return (url.scheme in ("https", "http") and valid_host(url.hostname or "")
                and not url.username and not url.password and not url.query
                and not url.fragment and url.path in ("", "/")
                and (url.port is None or 0 < url.port <= 65535))
    except ValueError:
        return False


def valid_version(value, component):
    major = "2" if component == "panel" else "1"
    return bool(re.fullmatch(r"v" + major + r"\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?", value))


def version_key(tag):
    nums = tuple(map(int, tag[1:].split("-")[0].split(".")))
    suffix = tag.split("-", 1)[1] if "-" in tag else ""
    rank = 3 if not suffix else {"alpha": 0, "beta": 1, "rc": 2}[suffix.split(".")[0]]
    return (*nums, rank, int(suffix.split(".")[1]) if suffix else 0)


def secure_extract(archive, destination, preserve_ownership=True):
    """Extrae archivos y symlinks internos; rechaza rutas externas/dispositivos."""
    destination = Path(destination).resolve()
    with tarfile.open(archive, "r:gz") as tar:
        members = [member for member in tar.getmembers() if not (member.isdir() and Path(member.name) == Path("."))]
        seen = set()
        previous = {}
        links = {Path(m.name) for m in members if m.issym()}
        for member in members:
            name = Path(member.name)
            target = (destination / name).resolve()
            if (name.is_absolute() or ".." in name.parts or not name.parts
                    or not target.is_relative_to(destination)
                    or not (member.isfile() or member.isdir() or member.issym() or member.islnk()) or member.name in seen
                    or any(parent in links for parent in name.parents)):
                raise InstallerError(f"Backup con entrada no permitida: {member.name}")
            if member.issym():
                link = Path(member.linkname)
                if link.is_absolute() or not (target.parent / link).resolve().is_relative_to(destination):
                    raise InstallerError(f"Backup con enlace externo: {member.name}")
            if member.islnk():
                source = previous.get(member.linkname)
                if source is None or not (source.isfile() or source.islnk()):
                    raise InstallerError("Backup con hardlink sin archivo original anterior.")
            seen.add(member.name)
            previous[member.name] = member
        # Los links se crean al final: nunca escribir a través de un link del tar.
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif member.isfile() or member.islnk():
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tar.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        for member in members:
            if member.issym():
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.symlink_to(member.linkname)
        for member in members:
            target = destination / member.name
            if member.issym():
                try:
                    internal = target.resolve().is_relative_to(destination)
                except RuntimeError as exc:
                    raise InstallerError("Backup con ciclo de enlaces.") from exc
                if not internal:
                    raise InstallerError("Backup con enlace que escapa del destino.")
            else:
                target.chmod(member.mode & 0o777 & ~0o002)
                if preserve_ownership and os.geteuid() == 0:
                    # .env debe seguir siendo legible para nginx dentro del contenedor.
                    os.chown(target, member.uid, member.gid)


from .ui import UI


class Runner:
    def __init__(self, ui, log):
        self.ui, self.log = ui, Path(log)
        self.secrets = set()

    def redact(self, text):
        for secret in sorted(self.secrets, key=len, reverse=True):
            if secret:
                text = text.replace(secret, "[OCULTO]")
        text = re.sub(r"(?i)((?:password|token(?:_id)?|app_key|hashids_salt)[\"']?\s*[:=]\s*)[^\s,]+",
                      r"\1[OCULTO]", text)
        text = re.sub(r"(?i)Bearer\s+\S+", "Bearer [OCULTO]", text)
        text = re.sub(r"ptl[a-z]_[A-Za-z0-9_-]+", "[TOKEN OCULTO]", text)
        return text

    def record(self, text):
        self.log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.log.open("a", encoding="utf-8") as stream:
            self.log.chmod(0o600)
            stream.write(self.redact(text) + "\n")

    def run(self, args, label=None, interactive=False, output=None, input_file=None,
            check=True, timeout=1800, env=None, umask=0o077, cwd=None):
        args = [str(arg) for arg in args]
        self.record("$ " + " ".join(args))
        # Archivos temporales evitan acumular dumps y salidas de apt en memoria.
        with tempfile.TemporaryFile() as captured, tempfile.TemporaryFile() as errors:
            with (self.ui.busy(label) if label and not interactive else contextlib.nullcontext()), (self.ui.suspend() if interactive else contextlib.nullcontext()):
                try:
                    result = subprocess.run(
                        args, stdin=input_file, stdout=None if interactive else (output or captured),
                        stderr=None if interactive else errors, check=False,
                        timeout=None if interactive else timeout,
                        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive", **(env or {})}, umask=umask, cwd=cwd)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise InstallerError(f"No se pudo ejecutar {args[0]}: {exc}") from exc
            captured.seek(0)
            errors.seek(0)
            text = captured.read().decode("utf-8", "replace")
            error = errors.read().decode("utf-8", "replace")
            self.record(text + error)
            if result.returncode and check:
                detail = self.redact((error + "\n" + text)[-4800:])
                raise InstallerError(f"Falló {label or args[0]} (código {result.returncode}).\n{detail}")
            return result.returncode, text


class Paths:
    def __init__(self, root=Path("/")):
        self.root = Path(root)
        self.base = self.root / "opt/pterodactyl-installer"
        self.panel = self.base / "panel"
        self.data = self.panel / "data"
        self.state = self.panel / "state.json"
        self.compose = self.panel / "compose.json"
        self.backups = self.root / "var/backups/pterodactyl-installer"
        self.log = self.root / "var/log/pterodactyl-installer/installer.log"
        self.wings = self.root / "usr/local/bin/wings"
        self.wings_state = self.base / "wings.json"
        self.config_dir = self.root / "etc/pterodactyl"
        self.config = self.config_dir / "config.yml"
        self.service = self.root / "etc/systemd/system/wings.service"
        self.hook = self.root / "etc/letsencrypt/renewal-hooks/deploy/ptero-wings.sh"


class Installer:
    def __init__(self, paths=None, ui=None, runner=None):
        self.p = paths or Paths()
        self.ui = ui or UI()
        self.run = runner or Runner(self.ui, self.p.log)

    def load(self, path):
        state = read_json(path)
        if not isinstance(state, dict) or state.get("schema") != SCHEMA or state.get("owner") != PROJECT:
            raise InstallerError("La instalación o copia no pertenece a este instalador.")
        if Path(path) == self.p.wings_state and self.p.config.is_file():
            text = self.p.config.read_text()
            if text.lstrip().startswith("{"):
                config = json.loads(text)
                self.run.secrets.update(str(config.get(key, "")) for key in ("token", "token_id"))
            else:
                for match in re.finditer(r"(?m)^token(?:_id)?:\s*[\"']?([A-Za-z0-9_-]+)", text):
                    self.run.secrets.add(match[1])
        return state

    def panel_state(self):
        if not self.p.state.is_file():
            raise InstallerError("Install the Panel first. Start with Install Panel or Install Panel and Wings.")
        state = self.load(self.p.state)
        settings = state.get("game_database", {})
        credentials = [state.get("db_password"), state.get("mail_password", ""), state.get("redis_password", "")]
        if not isinstance(settings, dict) or not all(isinstance(value, str) for value in credentials):
            raise InstallerError("La instalación o copia no pertenece a este instalador.")
        if not isinstance(settings.get("password", ""), str):
            raise InstallerError("La instalación o copia no pertenece a este instalador.")
        self.run.secrets.update([state["db_password"], state.get("mail_password", "")])
        self.run.secrets.add(state.get("redis_password", ""))
        self.run.secrets.add(settings.get("password", ""))
        return state

    def save_panel(self, state):
        write_json(self.p.state, state)
        if state.get("method", "docker") == "docker":
            if state.get("database_engine") == "mysql":
                # The bundled MariaDB CLI otherwise rejects MySQL's generated
                # private-cluster certificate during Laravel schema loading.
                atomic_write(self.p.data / "mysql-client.cnf", "[client]\nssl-verify-server-cert=0\n", 0o644)
            write_json(self.p.compose, self.compose_config(state))

    def compose_config(self, state):
        env = {
            "APP_URL": state["url"], "APP_TIMEZONE": state["timezone"],
            "APP_SERVICE_AUTHOR": state["email"], "APP_ENV": "production",
            "APP_DEBUG": "false", "APP_ENVIRONMENT_ONLY": "true",
            "DB_HOST": "database", "DB_PORT": "3306", "DB_DATABASE": "panel",
            "DB_USERNAME": "pterodactyl", "DB_PASSWORD": state["db_password"],
            "CACHE_STORE": "redis", "SESSION_DRIVER": "redis", "SESSION_CONNECTION": "sessions",
            "QUEUE_CONNECTION": "redis", "REDIS_HOST": "cache", "REDIS_QUEUE_RETRY_AFTER": "90",
            "QUEUE_WORKER_ENABLED": "true", "SCHEDULER_ENABLED": "true",
            "MAIL_MAILER": state.get("mail_mailer", "log"), "MAIL_FROM_ADDRESS": state["email"],
            "MAIL_HOST": state.get("mail_host", ""), "MAIL_PORT": state.get("mail_port", "587"),
            "MAIL_USERNAME": state.get("mail_user", ""), "MAIL_PASSWORD": state.get("mail_password", ""),
            "MAIL_ENCRYPTION": state.get("mail_encryption", "tls"),
            "SESSION_SECURE_COOKIE": "true" if state["url"].startswith("https://") else "false",
            "LE_EMAIL": state["email"] if state.get("tls") else "",
        }
        # Compose interpola $ incluso en JSON; $$ transmite un dólar literal.
        env = {key: str(value).replace("$", "$$") for key, value in env.items()}
        mounts = [("var", "/app/var"), ("nginx", "/etc/nginx/http.d"),
                  ("certs", "/etc/letsencrypt"), ("logs", "/app/storage/logs"),
                  ("extensions", "/app/extensions"), ("extension-assets", "/app/public/assets/extensions")]
        volumes = lambda name, target: {"type": "bind", "source": str(self.p.data / name), "target": target}
        config = {"name": PROJECT, "services": {
            "database": {"image": state.get("database_image", "mysql:8.4" if state.get("database_engine") == "mysql" else "mariadb:11.4"),
                         "restart": "unless-stopped", "volumes": [volumes("database", "/var/lib/mysql")],
                         "environment": {"MARIADB_PASSWORD": state["db_password"],
                                         "MARIADB_RANDOM_ROOT_PASSWORD": "yes", "MARIADB_DATABASE": "panel",
                                         "MARIADB_USER": "pterodactyl"},
                         "healthcheck": {"test": ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"],
                                         "interval": "10s", "timeout": "5s", "retries": 15, "start_period": "30s"}},
            "cache": {"image": state.get("cache_image", "redis:7.4-alpine"), "restart": "unless-stopped",
                      "command": ["redis-server", "--appendonly", "yes"],
                      "volumes": [volumes("redis", "/data")],
                      "healthcheck": {"test": ["CMD", "redis-cli", "ping"], "interval": "10s",
                                      "timeout": "5s", "retries": 10}},
            "panel": {"image": state.get("panel_image", "ghcr.io/pterodactyl/panel:" + state["version"]),
                      "restart": "unless-stopped", "stop_grace_period": "90s",
                      "ports": [f"{state['bind']}:{state['http_port']}:80"] +
                               ([f"{state['bind']}:{state['https_port']}:443"] if state.get("tls") else []),
                      "depends_on": {key: {"condition": "service_healthy"} for key in ("database", "cache")},
                      "volumes": [volumes(name, target) for name, target in mounts], "environment": env}
        }}
        if state.get("database_engine") == "mysql":
            config["services"]["panel"]["volumes"].append({"type": "bind", "source": str(self.p.data / "mysql-client.cnf"),
                "target": "/etc/my.cnf.d/ptero-installer.cnf", "read_only": True})
            config["services"]["panel"]["volumes"].append({"type": "bind", "source": str(self.p.data / "mysql-plugins"),
                "target": "/usr/lib/mariadb/plugin", "read_only": True})
            db = config["services"]["database"]
            db["image"] = state.get("database_image", "mysql:8.4")
            db["environment"] = {"MYSQL_RANDOM_ROOT_PASSWORD": "yes", "MYSQL_DATABASE": "panel",
                                 "MYSQL_USER": "pterodactyl", "MYSQL_PASSWORD": state["db_password"]}
            db["healthcheck"]["test"] = ["CMD-SHELL", 'MYSQL_PWD="$$MYSQL_PASSWORD" mysql --host=127.0.0.1 --user="$$MYSQL_USER" --database="$$MYSQL_DATABASE" --execute="SELECT 1" --silent']
        return config

    def dc(self, *args, **kwargs):
        return self.run.run(["docker", "compose", "--project-name", PROJECT, "--file", self.p.compose,
                             *args], **kwargs)

    def prepare_mysql_client(self, state):
        if state.get("method", "docker") != "docker" or state.get("database_engine") != "mysql":
            return
        directory = self.p.data / "mysql-plugins"
        plugin = directory / "caching_sha2_password.so"
        source = state["panel_image"]
        if (plugin.is_file() and state.get("mysql_plugin_image") == source
                and state.get("mysql_plugin_arch") == platform.machine()
                and hashlib.sha256(plugin.read_bytes()).hexdigest() == state.get("mysql_plugin_sha256")):
            return
        directory.mkdir(parents=True, exist_ok=True, mode=0o755)
        directory.chmod(0o755)
        self.run.run(["docker", "run", "--rm", "--entrypoint", "sh", "--mount",
                      f"type=bind,source={directory},target=/ptero-plugins", source, "-c",
                      "apk add --no-cache mariadb-connector-c && cp /usr/lib/mariadb/plugin/caching_sha2_password.so /ptero-plugins/caching_sha2_password.so && chmod 644 /ptero-plugins/caching_sha2_password.so"],
                     label="Preparing the MySQL authentication client", timeout=600)
        if not plugin.is_file():
            raise InstallerError("The MySQL authentication client was not prepared.")
        state.update(mysql_plugin_image=source, mysql_plugin_arch=platform.machine(),
                     mysql_plugin_sha256=hashlib.sha256(plugin.read_bytes()).hexdigest())
        self.save_panel(state)

    def check_host(self, wings=False):
        if os.geteuid() != 0:
            raise InstallerError("Ejecuta con sudo o como root.")
        release = {}
        for line in (self.p.root / "etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                release[key] = value.strip('"')
        supported = {"ubuntu": ("22.04", "24.04", "26.04"), "debian": ("12", "13")}
        if release.get("VERSION_ID") not in supported.get(release.get("ID"), ()):
            raise InstallerError("Sistemas admitidos: Ubuntu 22.04/24.04/26.04 y Debian 12/13.")
        if platform.machine() not in ("x86_64", "aarch64"):
            raise InstallerError("Arquitectura admitida: amd64 o arm64.")
        if not (self.p.root / "run/systemd/system").is_dir():
            raise InstallerError("Se necesita un VPS/servidor con systemd como sistema de inicio.")
        if shutil.disk_usage(self.p.root).free < 4 * 1024**3:
            raise InstallerError("Se necesitan al menos 4 GiB libres para las imágenes y la instalación.")
        meminfo = self.p.root / "proc/meminfo"
        if meminfo.exists():
            match = re.search(r"MemTotal:\s+(\d+)", meminfo.read_text())
            if match and int(match[1]) < 2 * 1024**2:
                self.ui.say("Se recomiendan al menos 2 GiB de RAM, más la memoria de tus juegos.", "warn")
        if wings:
            _, virt = self.run.run(["systemd-detect-virt"], check=False)
            if virt.strip() in ("openvz", "lxc", "lxc-libvirt", "docker", "podman"):
                raise InstallerError(f"Wings requiere Docker en un host compatible; virtualización: {virt.strip()}.")
        return release

    def docker(self):
        release = self.check_host()
        installed = bool(shutil.which("docker"))
        has_compose = installed and self.run.run(["docker", "compose", "version"], check=False)[0] == 0
        if not has_compose:
            self.ui.say("Se instalará Docker Engine/Compose desde el repositorio oficial de Docker.")
            self.run.run(["apt-get", "update"], label="Actualizando índices APT")
            self.run.run(["apt-get", "install", "-y", "ca-certificates", "curl"], label="Dependencias de Docker")
            distro = release["ID"]
            key = self.p.root / "etc/apt/keyrings/docker.asc"
            key.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            data = self.fetch(f"https://download.docker.com/linux/{distro}/gpg").decode("ascii")
            if "BEGIN PGP PUBLIC KEY BLOCK" not in data:
                raise InstallerError("Clave del repositorio Docker no válida.")
            atomic_write(key, data, 0o644)
            arch = "amd64" if platform.machine() == "x86_64" else "arm64"
            codename = release.get("VERSION_CODENAME", "")
            if not re.fullmatch(r"[a-z]+", codename):
                raise InstallerError("No se pudo determinar el codename de APT.")
            source = (f"deb [arch={arch} signed-by={key}] https://download.docker.com/linux/{distro} "
                      f"{codename} stable\n")
            atomic_write(self.p.root / "etc/apt/sources.list.d/ptero-docker.list", source, 0o644)
            self.run.run(["apt-get", "update"], label="Consultando repositorio Docker")
            packages = ["docker-compose-plugin"] if installed else [
                "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"]
            self.run.run(["apt-get", "install", "-y", *packages], label="Instalando Docker y Compose")
        self.run.run(["systemctl", "enable", "--now", "docker"], label="Iniciando Docker")
        self.run.run(["docker", "info"], label="Verificando Docker")

    def fetch(self, url, limit=8 * 1024 * 1024):
        headers = {"User-Agent": "ptero-installer/" + __version__, "Accept": "application/json"}
        token = os.environ.get("PTERO_GITHUB_TOKEN")
        parsed = urllib.parse.urlsplit(url)
        if token and parsed.scheme == "https" and parsed.hostname == "api.github.com":
            self.run.secrets.add(token)
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = response.read(limit + 1)
            if len(result) > limit:
                raise InstallerError("Respuesta remota demasiado grande.")
            return result
        except (urllib.error.URLError, TimeoutError) as exc:
            raise InstallerError(f"No se pudo descargar {url}: {exc}") from exc

    def release(self, component, version):
        base = f"https://api.github.com/repos/pterodactyl/{component}/releases"
        if version == "auto":
            with self.ui.busy("Checking official releases"):
                releases = json.loads(self.fetch(base + "?per_page=100"))
            candidates = [item for item in releases if not item["draft"]
                          and valid_version(item["tag_name"], component)
                          and (component != "wings" or not item["prerelease"])]
            if not candidates:
                raise InstallerError(f"No hay releases oficiales compatibles para {component}.")
            release = max(candidates, key=lambda item: version_key(item["tag_name"]))
        else:
            if not valid_version(version, component):
                raise InstallerError("Versión no válida o de otra rama principal.")
            with self.ui.busy("Checking official releases"):
                release = json.loads(self.fetch(base + "/tags/" + version))
        if release.get("draft") or not valid_version(release.get("tag_name", ""), component):
            raise InstallerError("GitHub no devolvió una release compatible.")
        return release

    def choose_release(self, component, default):
        version = self.ui.ask(f"Versión de {component} (auto busca la más reciente compatible)", default,
                              lambda x: x == "auto" or valid_version(x, component))
        release = self.release(component, version)
        self.ui.say(f"Versión elegida: {release['tag_name']}")
        if release["prerelease"] and not self.ui.yes("Es una versión de pruebas. ¿Continuar?"):
            raise Cancelled("Instalación beta cancelada.")
        return release

    def pin_image(self, ref):
        self.run.run(["docker", "pull", ref], label=f"Downloading {ref}", timeout=3600)
        _, text = self.run.run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ref])
        digests = json.loads(text)
        if not digests or not re.fullmatch(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}", digests[0]):
            raise InstallerError("La imagen descargada no tiene un digest verificable.")
        return digests[0]

    def port_free(self, address, port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((address, port))
        except OSError as exc:
            raise InstallerError(f"Puerto {address}:{port} ocupado o no disponible.") from exc

    def new_panel(self):
        from .wizard import panel_plan
        return panel_plan(self)

    def native(self, state=None):
        from .native import NativeBackend
        return NativeBackend(self, state or self.panel_state())

    def check_plan(self, state):
        if state["method"] == "standalone":
            release = self.check_host()
            if state["database_engine"] == "mysql" and release["ID"] == "debian" and platform.machine() != "x86_64":
                raise InstallerError("Native MySQL on Debian requires amd64. Choose MariaDB or Docker on ARM64.")
            backend = self.native(state)
            backend.check_php_availability(release)
            if backend.app.exists() and any(backend.app.iterdir()):
                raise InstallerError("The standalone application directory already exists; unmanaged files will not be overwritten.")
            for path in (backend.site, backend.enabled, backend.pool, backend.redis_config, backend.units / backend.redis_unit):
                if path.exists():
                    raise InstallerError("A reserved standalone configuration already exists: " + str(path))
            self.port_free("127.0.0.1", 16379)
        for port in ([80, 443] if state["tls"] else [state["http_port"]]):
            self.port_free(state["bind"], port)

    def create_admin(self, state):
        if "admin" not in state:
            self.dc("run", "--rm", "panel", "php", "artisan", "p:user:make", "--admin=1", interactive=True)
            return
        if not getattr(self, "admin_password", None):
            self.admin_password = self.ui.ask("Administrator password (12+ characters)", secret=True,
                                              validator=lambda value: len(value) >= 12)
        from .admin import create
        if state.get("method") == "standalone":
            backend = self.native(state)
            create(self, state, ["runuser", "-u", "www-data", "--", backend.php], backend.app)
        else:
            create(self, state, ["docker", "compose", "--project-name", PROJECT, "--file", self.p.compose,
                                "run", "--rm", "-T", "panel", "php"], "/app")

    @staticmethod
    def valid_port(value):
        return value.isdigit() and 1 <= int(value) <= 65535

    @staticmethod
    def is_ipv4(value):
        try:
            return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
        except ValueError:
            return False

    def smtp_settings(self, state):
        state.update(mail_mailer="smtp",
                     mail_host=self.ui.ask("Host SMTP", validator=valid_host),
                     mail_port=self.ui.ask("Puerto SMTP", "587", self.valid_port),
                     mail_user=self.ui.ask("Usuario SMTP"),
                     mail_password=self.ui.ask("Contraseña SMTP", secret=True),
                     mail_encryption=self.ui.ask("Cifrado SMTP (tls/ssl/null)", "tls",
                                                 lambda s: s in ("tls", "ssl", "null")))
        self.run.secrets.add(state["mail_password"])

    def existing_game_database(self):
        from .game_database import GameDatabase
        database = GameDatabase(self)
        return database.load() if database.state_file.exists() else None

    def install_panel(self):
        self.check_host()
        if self.p.state.exists():
            state = self.panel_state()
            if state["status"] == "restoring":
                raise InstallerError("Restauración SQL incompleta. Conserva el backup y repite la restauración en un destino vacío.")
            if state["status"] == "ready":
                self.ui.say("El Panel ya está instalado. Usa actualizar, reiniciar o configurar SMTP.", "ok")
                if state.get("game_database", {}).get("mode", "later") != "later" and not state["game_database"].get("registered"):
                    self.setup_game_database(state)
                return
            self.ui.say(f"Instalación gestionada existente: {state['status']}, {state['version']}.")
            self.ui.confirm("REANUDAR PANEL")
        else:
            if self.p.panel.exists() and any(self.p.panel.iterdir()):
                raise InstallerError("El directorio de destino contiene archivos sin registro; no se sobrescriben.")
            state = self.new_panel()
            self.save_panel(state)
        if state.get("method") == "standalone":
            return self.native(state).install()
        from .phases import Phases
        phases = Phases(self, state, lambda: self.save_panel(state))
        phases.run("Docker runtime", self.docker)
        self.run.secrets.add(state["db_password"])
        for name in ("database", "redis", "var", "nginx", "certs", "logs", "extensions", "extension-assets"):
            (self.p.data / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        # El entrypoint da .env a nginx, pero no cambia el dueño de /app/var.
        # El bind mount debe permitir a nginx atravesar ese directorio.
        # Los padres privados de /opt protegen los secretos en el host.
        (self.p.data / "var").chmod(0o755)
        for key, ref in (("panel_image", "ghcr.io/pterodactyl/panel:" + state["version"]),
                         ("database_image", "mysql:8.4" if state.get("database_engine") == "mysql" else "mariadb:11.4"),
                         ("cache_image", "redis:7.4-alpine")):
            if key not in state:
                state[key] = self.pin_image(ref)
                self.save_panel(state)
        self.prepare_mysql_client(state)
        self.dc("config", "--quiet")
        phases.run("SQL and cache", lambda: self.dc("up", "-d", "--wait", "--wait-timeout", "240", "database", "cache", label="Preparando base de datos y Redis"))
        self.dc("stop", "panel", label="Manteniendo el Panel detenido durante las migraciones")
        phases.run("Panel migrations", lambda: self.dc("run", "--rm", "-T", "panel", "php", "artisan", "migrate", "--seed", "--force", "--no-interaction",
                label="Migraciones y eggs oficiales"))
        if not state.get("admin_created"):
            self.ui.say("Creating the first administrator")
            self.create_admin(state)
            state["admin_created"] = True
            self.save_panel(state)
        phases.run("Service health", lambda: self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel", label="Iniciando Panel, colas y scheduler"))
        state["status"] = "ready"
        self.save_panel(state)
        self.ui.say(f"Panel disponible: {state['url']}", "ok")
        self.ui.say("Guarda fuera del servidor una copia de data/var/.env (APP_KEY y HASHIDS_SALT).")
        self.setup_game_database(state)

    def setup_game_database(self, state=None):
        from .game_database import GameDatabase
        return GameDatabase(self).setup(state or self.panel_state())

    def configure_game_database(self):
        from .game_database import plan
        state = self.panel_state()
        if state["status"] != "ready":
            raise InstallerError("El Panel no está listo; reanuda la instalación/actualización primero.")
        state["game_database"] = plan(self, state, advanced=True)
        self.ui.confirm("CONFIGURE DATABASE HOST")
        self.save_panel(state)
        self.setup_game_database(state)

    def game_database_credentials(self):
        from .game_database import GameDatabase
        GameDatabase(self).credentials(self.panel_state() if self.p.state.exists() else None)

    def backup_game_database(self):
        from .game_database import GameDatabase
        return GameDatabase(self).backup()

    def download_wings(self, release, target):
        arch = "amd64" if platform.machine() == "x86_64" else "arm64"
        name = "wings_linux_" + arch
        asset = next((a for a in release["assets"] if a["name"] == name), None)
        if not asset or not re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest") or ""):
            raise InstallerError("GitHub no publica un SHA-256 para este binario; se cancela la descarga.")
        url = asset["browser_download_url"]
        expected = f"https://github.com/pterodactyl/wings/releases/download/{release['tag_name']}/{name}"
        if url != expected:
            raise InstallerError("La descarga de Wings no corresponde al repositorio oficial.")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        digest = hashlib.sha256()
        try:
            with self.ui.busy("Descargando y verificando Wings"), urllib.request.urlopen(url, timeout=90) as response, target.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    stream.write(chunk)
            if "sha256:" + digest.hexdigest() != asset["digest"]:
                raise InstallerError("El SHA-256 de Wings no coincide. No se ejecutará el archivo.")
            target.chmod(0o755)
            self.run.run([target, "version"], label="Comprobando ejecutable Wings")
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    def service_text(self):
        return ("[Unit]\nDescription=Pterodactyl Wings\nAfter=docker.service network-online.target\n"
                "Wants=network-online.target\nRequires=docker.service\nPartOf=docker.service\n"
                "StartLimitIntervalSec=180\nStartLimitBurst=30\n\n[Service]\nUser=root\n"
                f"WorkingDirectory={self.p.config_dir}\nLimitNOFILE=65536\n"
                f"ExecStart={self.p.wings} --config {self.p.config}\nRestart=on-failure\nRestartSec=5s\n"
                "\n[Install]\nWantedBy=multi-user.target\n")

    def install_wings(self):
        self.ui.step(1, 3, "Wings installation")
        self.check_host(wings=True)
        if self.p.wings_state.exists():
            state = self.load(self.p.wings_state)
            if state.get("method") == "docker":
                from .wings import DockerWings
                DockerWings(self, state).save()
                self.ui.say("Wings container already installed. Use configure or update.")
                return
            if self.p.wings.exists() and self.p.service.exists():
                self.ui.say(f"Wings ya está gestionado ({state['status']}). Usa configurar o actualizar.")
                return
            self.ui.say("Instalación de Wings interrumpida: se reparará la versión registrada.", "warn")
            release = self.release("wings", state["version"])
        else:
            if any(path.exists() for path in (self.p.wings, self.p.config, self.p.service)):
                raise InstallerError("Hay una instalación de Wings ajena a este script; no se sobrescribe.")
            release = self.choose_release("wings", WINGS_VERSION)
        method = state.get("method", "standalone") if self.p.wings_state.exists() else self.ui.choice("Wings deployment", [
            ("standalone", "Standalone daemon (Recommended)", "A systemd service managing Docker game containers"),
            ("docker", "Docker container", "A Wings container with host networking and Docker socket access")])
        self.ui.confirm("INSTALAR WINGS")
        self.ui.step(2, 3, "Deploying Wings")
        self.docker()
        if method == "docker":
            from .wings import DockerWings
            state = {"schema": SCHEMA, "owner": PROJECT, "method": "docker", "version": release["tag_name"],
                     "status": "pending", "image": self.pin_image("ghcr.io/pterodactyl/wings:" + release["tag_name"])}
            DockerWings(self, state).save()
            if self.ui.yes("¿Vincular Wings al Panel ahora?", True):
                self.configure_wings()
            else:
                self.ui.say("Wings queda detenido hasta completar «Configurar Wings».", "warn")
            return
        staged = self.p.wings.with_name(".wings-installer-new")
        self.download_wings(release, staged)
        self.p.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Registrar antes de publicar: un fallo posterior permite reanudar/configurar.
        write_json(self.p.wings_state, {"schema": SCHEMA, "owner": PROJECT, "version": release["tag_name"],
                                       "status": "pending"})
        os.replace(staged, self.p.wings)
        atomic_write(self.p.service, self.service_text(), 0o644)
        self.run.run(["systemctl", "daemon-reload"])
        self.ui.say("Binario Wings instalado y verificado. Falta vincular el nodo.", "ok")
        if self.ui.yes("¿Vincular Wings al Panel ahora?", True):
            self.configure_wings()
        else:
            self.ui.say("Wings queda detenido hasta completar «Configurar Wings».", "warn")

    def configure_wings(self):
        state = self.load(self.p.wings_state)
        if self.p.state.exists() and self.panel_state().get("status") == "ready":
            method = self.ui.choice("Node connection method", [("automatic", "Create node automatically (Recommended)", "Create location, node and allocations, then configure Wings"), ("manual", "Use an existing node token", "Link a node already created in the Panel")])
            if method == "automatic":
                return self.create_node()
        self.ui.step(3, 3, "Node connection")
        from .node_plan import connection
        known = self.panel_state() if self.p.state.exists() else None
        url, node, token = connection(self, known["url"] if known else None)
        if self.p.config.exists():
            self.ui.say("Se genera una configuración nueva. Reaplica tus ajustes manuales desde la copia si los necesitas.", "warn")
            self.backup_wings()
        self.docker()
        # Mismo endpoint que wings configure; HTTPS con verificación y sin token en argv.
        endpoint = url + f"/api/application/nodes/{node}/configuration"
        request = urllib.request.Request(endpoint, headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.pterodactyl.v1+json",
            "User-Agent": "ptero-installer/" + __version__})
        try:
            with self.ui.busy("Obteniendo configuración del nodo"), urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise InstallerError("Configuración del nodo demasiado grande.")
            config = node_configuration(json.loads(body), url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise InstallerError("No se pudo obtener la configuración. Comprueba URL, ID y token Auto-Deploy.") from exc
        self.run.secrets.update((config["token"], config["token_id"]))
        # JSON es un subconjunto de YAML y Wings completa los valores predeterminados.
        from .networking import wings_network
        wings_network(self, config)
        write_json(self.p.config, config)
        if state.get("method", "standalone") == "standalone":
            atomic_write(self.p.service, self.service_text(), 0o644)
            self.run.run(["systemctl", "daemon-reload"])
        state.update(status="configured", panel_url=url, node=node)
        write_json(self.p.wings_state, state)
        self.ui.say("Si el Panel usa HTTPS, activa SSL en el nodo y emite su certificado antes de iniciar.")
        if self.ui.yes("¿Emitir certificado SSL para Wings ahora?"):
            self.wings_tls()
        self.start_wings()

    def start_wings(self):
        state = self.load(self.p.wings_state)
        if state.get("method") == "docker":
            from .wings import DockerWings
            return DockerWings(self, state).start()
        self.run.run(["systemctl", "enable", "wings"], label="Activando Wings")
        self.run.run(["systemctl", "restart", "wings"], label="Iniciando Wings con la configuración actual")
        # systemctl start puede devolver éxito antes de que Wings termine de arrancar.
        with self.ui.busy("Comprobando estabilidad inicial de Wings"):
            for _ in range(10):
                time.sleep(1)
                self.run.run(["systemctl", "is-active", "--quiet", "wings"])
        state = self.load(self.p.wings_state)
        state["status"] = "ready"
        write_json(self.p.wings_state, state)
        self.ui.say("Wings está activo. Comprueba que el nodo aparece conectado en el Panel.", "ok")

    def wings_tls(self):
        self.load(self.p.wings_state)
        if self.p.state.exists() and self.panel_state().get("method") == "standalone":
            return self.native().wings_tls()
        domain = self.ui.ask("Dominio de Wings, ej. node.ejemplo.com", validator=valid_domain)
        email = self.ui.ask("Correo Let's Encrypt", validator=valid_email)
        self.ui.say("En Configuration del nodo activa SSL y usa estas rutas:")
        self.ui.say(f"/etc/letsencrypt/live/{domain}/fullchain.pem\n/etc/letsencrypt/live/{domain}/privkey.pem")
        self.ui.say("El dominio debe apuntar a este host y permitir desafíos HTTP en el puerto 80.")
        panel = self.panel_state() if self.p.state.exists() else None
        if panel and panel["http_port"] == 80:
            self.ui.say("El Panel se pausará brevemente al emitir/renovar este certificado para liberar el puerto 80.", "warn")
        self.ui.confirm("EMITIR SSL WINGS")
        self.run.run(["apt-get", "update"], label="Actualizando APT")
        self.run.run(["apt-get", "install", "-y", "certbot"], label="Instalando Certbot")
        pre = self.p.root / "usr/local/sbin/ptero-acme-pre"
        post = self.p.root / "usr/local/sbin/ptero-acme-post"
        flag = self.p.root / "run/ptero-acme-panel-running"
        command = f"docker compose --project-name {PROJECT} --file {shlex.quote(str(self.p.compose))}"
        atomic_write(pre, "#!/bin/sh\nset -eu\n" +
                     f"if [ -f {shlex.quote(str(self.p.compose))} ] && {command} ps --services --status running | grep -qx panel; then\n" +
                     f"  touch {shlex.quote(str(flag))}\n  {command} stop panel\nfi\n", 0o700)
        atomic_write(post, "#!/bin/sh\nset -eu\n" +
                     f"if [ -f {shlex.quote(str(flag))} ]; then\n  {command} up -d panel\n" +
                     f"  rm -f {shlex.quote(str(flag))}\nfi\n", 0o700)
        atomic_write(self.p.hook, self.wings_renew_hook(), 0o700)
        was_running = panel and panel["http_port"] == 80 and "panel" in self.running_services()
        try:
            if was_running:
                self.dc("stop", "panel", label="Liberando puerto 80 para el certificado del nodo")
            self.port_free("0.0.0.0", 80)
            self.run.run(["certbot", "certonly", "--standalone", "--non-interactive", "--agree-tos",
                          "--email", email, "-d", domain, "--pre-hook", pre, "--post-hook", post],
                         label="Emitiendo certificado Wings")
        finally:
            if was_running:
                self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel")
        self.run.run(["systemctl", "enable", "--now", "certbot.timer"])
        self.ui.say("Certificado emitido. Vuelve a sincronizar la configuración si cambiaste SSL en el Panel.", "ok")

    def wings_renew_hook(self):
        from .wings import renewal_hook
        return renewal_hook(self)

    def backup_wings(self):
        self.load(self.p.wings_state)
        self.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.p.backups / ("wings-" + self.stamp())
        target.mkdir(mode=0o700)
        for path in (self.p.wings_state, self.p.config, self.p.service, self.p.base / "wings-compose.json"):
            if path.exists():
                shutil.copy2(path, target / path.name)
                (target / path.name).chmod(0o600)
        self.ui.say(f"Configuración de Wings guardada: {target}", "ok")
        return target

    @staticmethod
    def stamp():
        return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3)

    def database_command(self, state, dump=False):
        mysql = state.get("database_engine") == "mysql"
        user, password, database = (("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE") if mysql
                                    else ("MARIADB_USER", "MARIADB_PASSWORD", "MARIADB_DATABASE"))
        binary = ("mysqldump" if mysql else "mariadb-dump") if dump else ("mysql" if mysql else "mariadb")
        options = " --single-transaction --quick --hex-blob --triggers" if dump else ""
        if dump and mysql:
            options += " --no-tablespaces --column-statistics=0"
        return f'export MYSQL_PWD="${password}"; exec {binary} --user="${user}"{options} "${database}"'

    def running_services(self):
        _, text = self.dc("ps", "--services", "--status", "running")
        return set(text.split())

    def backup_panel(self):
        state = self.panel_state()
        if state.get("method") == "standalone":
            return self.native(state).backup()
        running = self.running_services()
        self.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.p.backups / ("panel-" + self.stamp() + ".tar.gz")
        temporary = target.with_suffix(".partial")
        try:
            with tempfile.TemporaryDirectory(prefix="backup-", dir=self.p.backups) as name:
                work = Path(name)
                try:
                    if "panel" in running:
                        self.dc("stop", "panel", label="Pausando Panel para una copia consistente")
                    if "database" not in running:
                        self.dc("up", "-d", "--wait", "--wait-timeout", "240", "database")
                    with (work / "database.sql").open("wb") as stream:
                        self.dc("exec", "-T", "database", "sh", "-c",
                                self.database_command(state, dump=True),
                                output=stream, label="Exportando base de datos")
                    if not (work / "database.sql").stat().st_size:
                        raise InstallerError("El dump SQL está vacío; no se acepta la copia.")
                    if "cache" in running:
                        self.dc("stop", "cache", label="Pausando Redis para guardar las colas")
                    write_json(work / "state.json", state)
                    write_json(work / "manifest.json", {"schema": SCHEMA, "owner": PROJECT, "type": "panel-backup"})
                    with self.ui.busy("Comprimiendo configuración, claves y datos"), tarfile.open(temporary, "w:gz", dereference=False) as tar:
                        for item in work.iterdir():
                            tar.add(item, arcname=item.name, recursive=True)
                        for item in self.p.data.iterdir():
                            if item.name not in ("database", "logs"):
                                tar.add(item, arcname="data/" + item.name, recursive=True)
                finally:
                    # Restaurar el estado previo incluso ante errores de disco/SQL.
                    if "cache" in running:
                        self.dc("up", "-d", "--wait", "cache")
                    if "panel" in running:
                        self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel")
                    if "database" not in running:
                        self.dc("stop", "database")
            temporary.chmod(0o600)
            os.replace(temporary, target)
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            atomic_write(Path(str(target) + ".sha256"), digest.hexdigest() + "\n")
            self.ui.say(f"Backup creado: {target} (contiene secretos; guárdalo fuera del servidor)", "ok")
            return target
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def restore_panel(self):
        archive = Path(self.ui.ask("Ruta absoluta al backup .tar.gz", validator=lambda s: Path(s).is_absolute() and Path(s).is_file()))
        checksum = Path(str(archive) + ".sha256")
        if not checksum.is_file():
            raise InstallerError("Falta el archivo .sha256 del backup.")
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != checksum.read_text().strip():
            raise InstallerError("El checksum del backup no coincide.")
        # La restauración se realiza en destino vacío para no mezclar claves ni esquemas.
        if self.p.panel.exists() and any(self.p.panel.iterdir()):
            raise InstallerError("El destino debe estar vacío. Desinstala/purga el Panel actual después de respaldarlo.")
        self.ui.confirm("RESTAURAR PANEL")
        self.p.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.p.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="restore-", dir=self.p.base) as name:
            work = Path(name)
            secure_extract(archive, work)
            manifest = self.load(work / "manifest.json")
            if manifest.get("type") != "panel-backup":
                raise InstallerError("El archivo no es un backup de Panel.")
            state = self.load(work / "state.json")
            if state.get("method") == "standalone":
                return self.native(state).restore(work)
            self.docker()
            if not (work / "data/var/.env").is_file() or not (work / "database.sql").is_file():
                raise InstallerError("La copia no contiene SQL y claves originales del Panel.")
            self.p.panel.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Mismo filesystem: conservar dueños, permisos y symlinks de certificados.
            os.replace(work / "data", self.p.data)
            state["status"] = "restoring"
            self.save_panel(state)
            self.run.secrets.add(state["db_password"])
            for folder in ("database", "logs", "redis", "nginx", "certs", "extensions", "extension-assets"):
                (self.p.data / folder).mkdir(exist_ok=True, mode=0o700)
            self.dc("pull", label="Descargando imágenes originales de la copia")
            self.prepare_mysql_client(state)
            self.dc("up", "-d", "--wait", "--wait-timeout", "240", "database", "cache")
            with (work / "database.sql").open("rb") as stream:
                self.dc("exec", "-T", "database", "sh", "-c",
                        self.database_command(state, dump=False),
                        input_file=stream, label="Restaurando SQL con sus claves originales")
            self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel", label="Arrancando Panel restaurado")
            state["status"] = "ready"
            self.save_panel(state)
        self.ui.say("Panel restaurado. Mantén el dominio/IP original o adapta DNS y configuración.", "ok")

    def update_panel(self):
        state = self.panel_state()
        if state["status"] != "ready":
            raise InstallerError("Completa/reanuda primero la instalación actual del Panel.")
        release = self.choose_release("panel", "auto")
        if release["tag_name"] == state["version"]:
            self.ui.say("Ya tienes esa versión.", "ok")
            return
        if version_key(release["tag_name"]) < version_key(state["version"]):
            raise InstallerError("No se permiten downgrades del Panel; restaura un backup de esa versión.")
        self.ui.confirm("ACTUALIZAR PANEL")
        if state.get("method") == "standalone":
            return self.native(state).update(release)
        # Descargar antes de interrumpir el Panel; copia antes de modificar el esquema.
        image = self.pin_image("ghcr.io/pterodactyl/panel:" + release["tag_name"])
        backup = self.backup_panel()
        self.dc("stop", "panel", label="Deteniendo Panel para actualizar")
        state.update(version=release["tag_name"], panel_image=image, status="updating", recovery_backup=str(backup))
        self.save_panel(state)
        try:
            self.prepare_mysql_client(state)
            self.dc("run", "--rm", "-T", "panel", "php", "artisan", "migrate", "--seed", "--force", "--no-interaction",
                    label="Aplicando migraciones de la versión nueva")
            self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel", label="Verificando nuevo Panel")
        except BaseException:
            self.ui.say(f"Actualización incompleta. Panel detenido; copia de recuperación: {backup}", "error")
            # No arrancar código viejo con un esquema que puede haber cambiado.
            self.dc("stop", "panel", check=False)
            raise
        state["status"] = "ready"
        self.save_panel(state)
        self.ui.say("Panel actualizado y comprobado por el healthcheck oficial.", "ok")

    def update_wings(self):
        state = self.load(self.p.wings_state)
        release = self.choose_release("wings", "auto")
        if release["tag_name"] == state["version"]:
            self.ui.say("Ya tienes esa versión.", "ok")
            return
        if state.get("method") == "docker":
            from .wings import DockerWings
            return DockerWings(self, state).update(release)
        self.ui.confirm("ACTUALIZAR WINGS")
        staged = self.p.wings.with_name(".wings-installer-new")
        old = self.p.wings.with_name(".wings-installer-old")
        self.download_wings(release, staged)
        backup = self.backup_wings()
        active = self.run.run(["systemctl", "is-active", "--quiet", "wings"], check=False)[0] == 0
        shutil.copy2(self.p.wings, old)
        try:
            if active:
                self.run.run(["systemctl", "stop", "wings"])
            os.replace(staged, self.p.wings)
            if active:
                self.start_wings()
            state["version"] = release["tag_name"]
            write_json(self.p.wings_state, state)
        except BaseException:
            os.replace(old, self.p.wings)
            if (backup / "config.yml").exists():
                shutil.copy2(backup / "config.yml", self.p.config)
            write_json(self.p.wings_state, state)
            if active:
                self.run.run(["systemctl", "restart", "wings"], check=False)
            raise
        finally:
            old.unlink(missing_ok=True)
            staged.unlink(missing_ok=True)
        self.ui.say("Wings actualizado; los contenedores de juegos se conservan.", "ok")

    def uninstall_panel(self, confirmed=False):
        state = self.panel_state()
        if state.get("method") == "standalone":
            return self.native(state).uninstall(confirmed)
        if not confirmed:
            self.ui.confirm("DESINSTALAR PANEL")
        purge = self.ui.yes("¿Borrar también base de datos y archivos del Panel? (antes se crea backup)")
        if purge:
            self.ui.confirm("BORRAR PANEL")
        backup = self.backup_panel()
        self.dc("down", label="Eliminando solo contenedores y red de este Panel")
        if purge:
            if self.p.panel.is_symlink() or self.p.panel.parent != self.p.base:
                raise InstallerError("Ruta de borrado no segura.")
            shutil.rmtree(self.p.panel)
        else:
            state["status"] = "stopped"
            self.save_panel(state)
        self.ui.say(f"Panel desinstalado. Backup: {backup}", "ok")
        if not purge:
            self.ui.say("Datos conservados. «Instalar Panel» permite reactivarlo.")

    def uninstall_wings(self, confirmed=False):
        state = self.load(self.p.wings_state)
        if state.get("method") == "docker":
            from .wings import DockerWings
            return DockerWings(self, state).uninstall(confirmed)
        if not confirmed:
            self.ui.confirm("DESINSTALAR WINGS")
        self.ui.say("Los juegos y sus contenedores seguirán existiendo. Apágalos desde el Panel si lo necesitas.", "warn")
        self.backup_wings()
        self.run.run(["systemctl", "disable", "--now", "wings"], label="Deteniendo y deshabilitando Wings")
        # Los hooks ACME siguen siendo necesarios para renovar certificados conservados.
        for path in (self.p.wings, self.p.service, self.p.config, self.p.wings_state):
            path.unlink(missing_ok=True)
        self.run.run(["systemctl", "daemon-reload"])
        self.ui.say("Wings desinstalado. Archivos de juegos, Docker y certificados conservados.", "ok")

    def uninstall_both(self):
        self.ui.confirm("DESINSTALAR PANEL Y WINGS")
        # Mantener Panel accesible si la copia o desinstalación de Wings falla.
        if self.p.wings_state.exists():
            self.uninstall_wings(confirmed=True)
        if self.p.state.exists():
            self.uninstall_panel(confirmed=True)

    def health_report(self):
        from .health import inspect
        return inspect(self)

    def create_node(self):
        from .nodes import setup
        return setup(self)

    def restore_game_database(self):
        from .backups import restore_sql
        return restore_sql(self)

    def backup_games(self):
        from .backups import backup_games
        self.ui.confirm("BACK UP GAME FILES")
        return backup_games(self)

    def restore_games(self):
        from .backups import restore_games
        return restore_games(self)

    def backup_schedule(self):
        from .backups import ScheduledBackups
        return ScheduledBackups(self).configure()

    def backup_run(self):
        from .backups import ScheduledBackups
        return ScheduledBackups(self).run_now()

    def backup_download(self):
        from .backups import ScheduledBackups
        return ScheduledBackups(self).download()

    def remote_node(self):
        from .remote import setup_node
        return setup_node(self)

    def remote_database(self):
        from .remote import setup_database
        return setup_database(self)

    def resume(self):
        if self.p.state.exists() and self.panel_state()["status"] != "ready":
            return self.install_panel()
        from .game_database import GameDatabase
        database = GameDatabase(self)
        if database.state_file.exists():
            saved = database.load()
            if saved.get("status") != "ready":
                self.ui.confirm("REANUDAR PANEL")
                database.local(saved)
                return
        if self.p.wings_state.exists() and self.load(self.p.wings_state)["status"] != "ready":
            return self.configure_wings()
        self.ui.say("No interrupted managed installation needs resuming.")

    def diagnostics(self):
        if self.p.state.exists() and self.panel_state().get("method") == "standalone":
            self.native().health()
            self.ui.say("Standalone services and HTTP endpoint passed their checks.", "ok")
        elif self.p.state.exists():
            self.run.run(["docker", "info", "--format", "{{.ServerVersion}}"])
            _, text = self.dc("ps", "--format", "json")
            found = set()
            for line in text.splitlines():
                data = json.loads(line)
                for service in (data if isinstance(data, list) else [data]):
                    found.add(service.get("Service"))
                    if service.get("State") != "running" or service.get("Health") != "healthy":
                        raise InstallerError("A Panel container is stopped or unhealthy.")
            if not {"database", "cache", "panel"}.issubset(found):
                raise InstallerError("Panel containers are missing.")
            self.ui.say("All Panel containers are healthy.", "ok")
        if self.p.wings_state.exists():
            state = self.load(self.p.wings_state)
            if state.get("method") == "docker":
                from .wings import DockerWings
                backend = DockerWings(self, state)
                backend.health()
                _, text = backend.dc("ps", "--all")
                self.ui.say(text)
            else:
                self.run.run(["systemctl", "is-active", "--quiet", "wings"])
                self.ui.say("Wings is active.", "ok")
        if not self.p.state.exists() and not self.p.wings_state.exists():
            self.ui.card("Ready for your first installation", [
                "No managed Panel or Wings is installed on this machine yet.",
                "Next: choose Install Panel and Wings, or install the Panel first."])
            self.ui.card("Machine overview", [
                self.ui.tr("Architecture: {value}").format(value=platform.machine()),
                self.ui.tr("Free disk space: {value} GiB").format(value=round(shutil.disk_usage(self.p.root).free / 1024 ** 3, 1)),
                self.ui.tr("System manager: {value}").format(value="systemd" if (self.p.root / "run/systemd/system").is_dir() else self.ui.tr("Not detected")),
                "Diagnostics do not install software or change firewall rules."])
            return
        self.ui.say(f"Log privado: {self.p.log}")

    def logs(self):
        if self.p.state.exists():
            state = self.panel_state()
            if state.get("method") == "standalone":
                _, text = self.run.run(["journalctl", "-u", "ptero-panel-queue", "-u", "ptero-panel-scheduler", "-n", "80", "--no-pager"])
            else:
                _, text = self.dc("logs", "--no-color", "--tail", "80")
            self.ui.say(self.run.redact(text))
        if self.p.wings_state.exists():
            state = self.load(self.p.wings_state)
            if state.get("method") == "docker":
                from .wings import DockerWings
                _, text = DockerWings(self, state).dc("logs", "--no-color", "--tail", "80")
            else:
                _, text = self.run.run(["journalctl", "-u", "wings", "-n", "80", "--no-pager"])
            self.ui.say(self.run.redact(text))

    def restart(self):
        self.ui.confirm("REINICIAR SERVICIOS")
        if self.p.state.exists():
            state = self.panel_state()
            if state["status"] != "ready":
                raise InstallerError("El Panel no está listo; reanuda la instalación/actualización primero.")
            if state.get("method") == "standalone":
                backend = self.native(state)
                self.run.run(["systemctl", "restart", backend.queue, backend.scheduler])
                backend.health()
            else:
                self.dc("restart", "panel", label="Reiniciando Panel")
                self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel")
        if self.p.wings_state.exists():
            self.start_wings()

    def mail(self):
        state = self.panel_state()
        self.smtp_settings(state)
        self.ui.confirm("CAMBIAR SMTP")
        self.save_panel(state)
        if state.get("method") == "standalone":
            backend = self.native(state)
            backend.application_environment()
            backend.artisan("config:clear")
            self.run.run(["systemctl", "restart", backend.queue])
            backend.health()
        else:
            self.dc("up", "-d", "--wait", "--wait-timeout", "360", "panel", label="Aplicando SMTP")

    def admin(self):
        state = self.panel_state()
        from .wizard import administrator
        state["admin"] = administrator(self)
        self.ui.confirm("CREATE ADMINISTRATOR")
        self.create_admin(state)
        if self.generated_admin_password:
            self.ui.card("Save your generated password", [self.admin_password])

    def firewall(self):
        self.ui.say("Permite en el firewall del proveedor y del host:")
        self.ui.say("Panel: TCP 80/443. Wings: TCP 8080 (o el puerto del nodo) y TCP 2022 para SFTP.")
        self.ui.say("Juegos: sus allocations TCP/UDP. SSH: conserva tu puerto de administración.")
        self.ui.say("Docker publica puertos mediante sus propias reglas; usa DOCKER-USER/nftables para restringirlos.")
        self.ui.say("No se activan firewalls ni se cambian reglas automáticamente.")

    def install_both(self):
        self.install_panel()
        self.install_wings()

    def actions(self):
        return {"install-all": self.install_both, "install-panel": self.install_panel,
                "install-wings": self.install_wings, "uninstall-all": self.uninstall_both,
                "uninstall-panel": self.uninstall_panel, "uninstall-wings": self.uninstall_wings,
                "update-panel": self.update_panel, "update-wings": self.update_wings,
                "configure-wings": self.configure_wings, "tls-wings": self.wings_tls,
                "backup-panel": self.backup_panel, "backup-wings": self.backup_wings,
                "restore-panel": self.restore_panel, "diagnose": self.diagnostics,
                "restart": self.restart, "logs": self.logs, "smtp": self.mail,
                "admin": self.admin, "firewall": self.firewall,
                "configure-database": self.configure_game_database,
                "database-credentials": self.game_database_credentials,
                "backup-game-database": self.backup_game_database,
                "create-node": self.create_node, "restore-game-database": self.restore_game_database,
                "backup-games": self.backup_games, "restore-games": self.restore_games,
                "backup-schedule": self.backup_schedule, "backup-run": self.backup_run,
                "backup-download": self.backup_download, "health": self.health_report,
                "resume": self.resume, "remote-node": self.remote_node, "remote-database": self.remote_database}

    def menu(self):
        from .cli import menu
        return menu(self)
