#!/usr/bin/env bash
# Online bootstrap: ask first, then fetch only the selected language package.
set -Eeuo pipefail
REPOSITORY="raimondarias/pterodactyl-installer"
VERSION="1.0.0.beta"
language=""
forwarded=()
while (($#)); do
    case "$1" in
        --language)
            [[ $# -ge 2 ]] || { printf '%s\n' 'Missing --language value.' >&2; exit 2; }
            language="$2"; shift 2 ;;
        --version) printf 'ptero-installer %s\n' "$VERSION"; exit 0 ;;
        --help|-h)
            printf '%s\n' 'Ptero Installer — online language bootstrap' \
                'Usage: bash install.sh [--language en|es|pt-BR] [--preview] [--no-animation] [action]' \
                'Without --language, the first question selects a language before downloading runtime code.' \
                'Offline source checkout: bash scripts/run_local.sh [options]'
            exit 0 ;;
        *) forwarded+=("$1"); shift ;;
    esac
done
if [[ -z "$language" ]]; then
    printf '\n  P T E R O  /  I N S T A L L E R\n\n'
    printf '%s\n' '  Which language would you like to use?' '' \
        '  1. English' '  2. Español' '  3. Português (Brasil)' ''
    while true; do
        printf '  Select [1]: '
        if ! IFS= read -r answer; then
            printf '\n%s\n' 'Input closed. No language package was downloaded.' >&2
            exit 130
        fi
        case "$answer" in
            1|'') language="en"; break ;;
            2) language="es"; break ;;
            3) language="pt-BR"; break ;;
            *) printf '%s\n' '  Invalid selection. Enter 1, 2 or 3.' ;;
        esac
    done
fi
case "$language" in en|es|pt-BR) ;; *) printf '%s\n' 'Invalid language. Use en, es or pt-BR.' >&2; exit 2 ;; esac

message() {
    case "$language:$1" in
        en:runtime) printf '%s\n' 'Preparing the Python runtime...' ;;
        es:runtime) printf '%s\n' 'Preparando el entorno de Python...' ;;
        pt-BR:runtime) printf '%s\n' 'Preparando o ambiente Python...' ;;
        en:python) printf '%s\n' 'Python 3 is required. Install python3, tzdata and ca-certificates, then retry.' ;;
        es:python) printf '%s\n' 'Se necesita Python 3. Instala python3, tzdata y ca-certificates y vuelve a intentarlo.' ;;
        pt-BR:python) printf '%s\n' 'É necessário Python 3. Instale python3, tzdata e ca-certificates e tente novamente.' ;;
        en:curl) printf '%s\n' 'curl is required to download the selected language package.' ;;
        es:curl) printf '%s\n' 'Se necesita curl para descargar el paquete del idioma seleccionado.' ;;
        pt-BR:curl) printf '%s\n' 'O curl é necessário para baixar o pacote do idioma selecionado.' ;;
        en:download) printf 'Downloading the %s installer from GitHub...\n' "$language" ;;
        es:download) printf 'Descargando el instalador %s desde GitHub...\n' "$language" ;;
        pt-BR:download) printf 'Baixando o instalador %s do GitHub...\n' "$language" ;;
        en:failed) printf '%s\n' 'The language package could not be verified or downloaded. No installer code was run.' ;;
        es:failed) printf '%s\n' 'No se pudo verificar o descargar el paquete del idioma. No se ejecutó el código del instalador.' ;;
        pt-BR:failed) printf '%s\n' 'Não foi possível verificar ou baixar o pacote do idioma. O código do instalador não foi executado.' ;;
    esac
}
command -v curl >/dev/null 2>&1 || { message curl >&2; exit 1; }
if ! command -v python3 >/dev/null 2>&1; then
    if [[ "$EUID" -ne 0 ]] || ! command -v apt-get >/dev/null 2>&1; then
        message python >&2; exit 1
    fi
    message runtime
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 tzdata ca-certificates
fi
umask 077
WORK_DIR="$(mktemp -d -t ptero-bootstrap.XXXXXXXX)"
trap 'rm -rf -- "$WORK_DIR"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
download() {
    curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
        --retry 2 --connect-timeout 15 --max-time 180 --max-filesize 16777216 "$1" --output "$2"
}
verified=0
trap 'if [[ "$verified" == 0 ]]; then message failed >&2; fi' ERR
# Resolve main once. All package and later language-change downloads use the
# same immutable commit, rather than mixing files from successive revisions.
message download
source_ref="${PTERO_SOURCE_REF:-}"
if [[ -z "$source_ref" ]]; then
    download "https://api.github.com/repos/$REPOSITORY/commits/main" "$WORK_DIR/commit.json"
    source_ref="$(python3 - "$WORK_DIR/commit.json" <<'PY'
import json, re, sys
with open(sys.argv[1]) as stream:
    value = json.load(stream).get('sha', '')
if not re.fullmatch(r'[0-9a-f]{40}', value):
    raise SystemExit('GitHub did not return a valid commit SHA.')
print(value)
PY
)"
fi
[[ "$source_ref" =~ ^[0-9a-f]{40}$ ]] || { message failed >&2; exit 1; }
base_url="https://raw.githubusercontent.com/$REPOSITORY/$source_ref/languages/$language"
download "$base_url/installer.tar.gz.sha256" "$WORK_DIR/package.sha256"
download "$base_url/installer.tar.gz" "$WORK_DIR/package.tar.gz"
python3 - "$WORK_DIR" "$language" "$REPOSITORY" "$VERSION" <<'PY'
import hashlib, json, re, sys, tarfile
from pathlib import Path, PurePosixPath
work, language, repository, version = Path(sys.argv[1]), *sys.argv[2:]
checksum = (work / 'package.sha256').read_text().strip()
if not re.fullmatch(r'[0-9a-f]{64}  installer\.tar\.gz', checksum):
    raise SystemExit('Invalid language package checksum file.')
archive = work / 'package.tar.gz'
if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum[:64]:
    raise SystemExit('Language package checksum mismatch.')
destination = work / 'runtime'
destination.mkdir(mode=0o700)
with tarfile.open(archive, 'r:gz') as package:
    members = package.getmembers()
    if len(members) > 1000 or sum(item.size for item in members) > 64 * 1024 * 1024:
        raise SystemExit('Language package exceeds extraction limits.')
    seen = set()
    for item in members:
        path = PurePosixPath(item.name)
        if (path.is_absolute() or '..' in path.parts or not path.parts or
                not (item.isfile() or item.isdir()) or path in seen):
            raise SystemExit('Unsafe or duplicate language package member.')
        seen.add(path)
    # Packages contain regular files/directories only; never materialize links,
    # devices, archive ownership or setuid permissions from a remote archive.
    for item in members:
        target = destination / item.name
        if item.isdir():
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with package.extractfile(item) as source, target.open('xb') as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
            target.chmod(0o600)
metadata = json.loads((destination / 'ptero/distribution.json').read_text())
if (metadata.get('language') != language or metadata.get('repository') != repository or
        metadata.get('version') != version):
    raise SystemExit('The language package does not match this bootstrap. Download install.sh again.')
for filename in ('installer.py', 'ptero/cli.py', 'scripts/run_local.sh'):
    if not (destination / filename).is_file():
        raise SystemExit('Incomplete language package.')
PY
verified=1
PTERO_SOURCE_REF="$source_ref" PTERO_SOURCE_REPOSITORY="$REPOSITORY" \
    bash "$WORK_DIR/runtime/scripts/run_local.sh" --language "$language" "${forwarded[@]}"
