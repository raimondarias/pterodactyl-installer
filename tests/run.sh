#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_DIR"
bash -n install.sh scripts/run_local.sh tests/run.sh
python3 -m compileall -q installer.py ptero tests scripts
python3 -m unittest discover -s tests -v
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck install.sh scripts/run_local.sh tests/run.sh
else
    printf '%s\n' 'ShellCheck unavailable; Bash syntax validation passed.'
fi
if [[ "${1:-}" == "--live" ]]; then
    python3 tests/live_check.py
fi
