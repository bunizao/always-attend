#!/bin/bash
#
# Always Attend - macOS launcher
# Relies on the Python portal experience for all interactive flows.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python 3.8+ is required. Install it from https://python.org/downloads/."
  read -r -p "Press Enter to exit..."
  exit 1
fi

echo "🚀 Launching Always Attend portal..."
exec "$PYTHON_BIN" main.py "$@"
