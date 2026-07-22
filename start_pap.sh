#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/stephan/venvs/standard/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

exec "$PYTHON" "$SCRIPT_DIR/pap_editor.py"