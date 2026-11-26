#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$DIR/configure.py" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$DIR/configure.py" "$@"
else
  echo "Error: Python 3 is required." >&2
  exit 1
fi
