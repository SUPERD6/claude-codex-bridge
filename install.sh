#!/usr/bin/env sh
# Install ccx from this clone (macOS / Linux). Usage: ./install.sh [hub-path] [--force]
# --force: switch this machine to hub-path although another hub is set (ccx init --force; the old hub stays as it is)
set -e
cd "$(dirname "$0")"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "ccx needs Python 3.11+")'
if command -v pipx >/dev/null 2>&1; then
  pipx install --force --editable .
else
  echo "pipx not found: add $(pwd)/bin to your PATH to use 'ccx' (or: python3 -m pip install --user -e .)"
fi
if [ -n "$1" ] && [ "$2" = "--force" ]; then python3 ccx.py init --hub "$1" --force
elif [ -n "$1" ]; then python3 ccx.py init --hub "$1"
else python3 ccx.py init; fi
python3 ccx.py doctor || true
echo
echo "Next: python3 ccx.py setup   (guided: explains each step and asks before changing anything)"
