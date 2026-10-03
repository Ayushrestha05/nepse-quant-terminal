#!/usr/bin/env bash
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

if [[ "${1:-}" == "--install-desktop" ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 is required to install the application-menu shortcut."
        exit 1
    fi
    exec python3 scripts/launch/bootstrap.py --install-desktop
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required to start NEPSE Quant Terminal."
    exit 1
fi

SYSTEM_PYTHON=$(command -v python3)
LAUNCH_INFO=$("$SYSTEM_PYTHON" scripts/launch/bootstrap.py --linux-launch-info)
STATUS=$?
if [[ "$STATUS" -ne 0 ]]; then
    exit "$STATUS"
fi
IFS=$'\t' read -r PYTHON_BIN VENV_DIRECTORY <<< "$LAUNCH_INFO"
if [[ -z "$PYTHON_BIN" || -z "$VENV_DIRECTORY" ]]; then
    echo "Could not select a supported Python runtime."
    exit 1
fi

exec "$PYTHON_BIN" scripts/launch/bootstrap.py --venv-directory "$VENV_DIRECTORY"
