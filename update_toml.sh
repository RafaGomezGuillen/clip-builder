#!/usr/bin/env sh
set -eu

CURRENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -x "$CURRENT_DIR/.venv/bin/python" ]; then
  PYTHON="$CURRENT_DIR/.venv/bin/python"
elif [ -x "$CURRENT_DIR/venv/bin/python" ]; then
  PYTHON="$CURRENT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=$(command -v python3)
else
  echo "Python 3.11 or newer was not found."
  exit 1
fi

exec "$PYTHON" "$CURRENT_DIR/update_toml.py" "$@"