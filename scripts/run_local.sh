#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
preview_mode=0
for argument in "$@"; do
    if [[ "$argument" == --preview ]]; then preview_mode=1; fi
done
if ! command -v python3 >/dev/null 2>&1; then
    if [[ "$preview_mode" == 1 || "${EUID}" -ne 0 ]] || ! command -v apt-get >/dev/null 2>&1; then
        printf '%s\n' 'Python 3 is required. Install it with: sudo apt-get install python3 tzdata ca-certificates' >&2
        exit 1
    fi
    printf '%s\n' 'Preparing Python 3 for the setup wizard...'
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 tzdata ca-certificates
fi
exec python3 "$SCRIPT_DIR/installer.py" "$@"
