#!/usr/bin/env python3
"""Read-only smoke check of the actual published GitHub distribution."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import installer as app
from ptero import __version__

REPOSITORY = "raimondarias/pterodactyl-installer"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ptero-installer-published-check"})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = response.read(16 * 1024 * 1024 + 1)
    if len(result) > 16 * 1024 * 1024:
        raise app.InstallerError("Published file exceeds the smoke check size limit.")
    return result


def main():
    commit = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/commits/main"))["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise app.InstallerError("GitHub did not return a commit SHA.")
    base = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}"
    bootstrap = fetch(f"https://raw.githubusercontent.com/{REPOSITORY}/main/install.sh")
    if bootstrap != fetch(base + "/install.sh") or f'VERSION="{__version__}"'.encode() not in bootstrap:
        raise app.InstallerError("The published bootstrap does not match the expected version/snapshot.")
    print(f"OK published main commit: {commit}", flush=True)
    print(f"OK published installer version: {__version__}", flush=True)
    environment = dict(os.environ)
    environment.pop("PTERO_SOURCE_REF", None)
    with tempfile.TemporaryDirectory(prefix="ptero-published-check-") as directory:
        work = Path(directory)
        launcher = work / "install.sh"
        launcher.write_bytes(bootstrap)
        for number, language, expected in ((1, "en", "Ready to install"),
                                            (2, "es", "Listo para instalar"),
                                            (3, "pt-BR", "Pronto para instalar")):
            result = subprocess.run(["bash", str(launcher), "--preview", "--no-animation"],
                                    input=f"{number}\n", text=True, capture_output=True,
                                    timeout=240, env=environment)
            if result.returncode or expected not in result.stdout or result.stdout.count("Which language would you like to use?") != 1:
                raise app.InstallerError(f"Published {language} preview failed: " + result.stderr[-2000:])
            print(f"OK real GitHub download and preview: {language}; one English language question", flush=True)
        payload = fetch(base + "/languages/en/installer.tar.gz")
        checksum = fetch(base + "/languages/en/installer.tar.gz.sha256").decode().split()[0]
        if hashlib.sha256(payload).hexdigest() != checksum:
            raise app.InstallerError("The published English archive checksum is invalid.")
        archive = work / "runtime.tar.gz"
        archive.write_bytes(payload)
        runtime = work / "runtime"
        app.secure_extract(archive, runtime, preserve_ownership=False)
        code = ("import json;from ptero.i18n import Translator;"
                "print(json.dumps({language:Translator(language)('Choose an option') "
                "for language in ('en','es','pt-BR')},ensure_ascii=False))")
        environment.update(PTERO_SOURCE_REF=commit, PYTHONPATH="")
        result = subprocess.run([sys.executable, "-c", code], cwd=runtime, capture_output=True,
                                text=True, env=environment, timeout=120)
        if result.returncode:
            raise app.InstallerError("Published language change failed: " + result.stderr[-2000:])
        translated = json.loads(result.stdout)
        if translated != {"en": "Choose an option", "es": "Elige una opción", "pt-BR": "Escolha uma opção"}:
            raise app.InstallerError("Published language changes returned unexpected translations.")
        print("OK real GitHub language changes: en -> es -> pt-BR; snapshot and hashes verified", flush=True)
    print("No Panel/Wings/system services were installed. Complete clean-VPS deployment remains untested.", flush=True)


if __name__ == "__main__":
    main()
