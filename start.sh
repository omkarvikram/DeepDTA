#!/bin/sh
set -eu
cd "$(dirname "$0")"
if command -v python3.11 >/dev/null 2>&1; then exec python3.11 start.py "$@"; fi
echo "Install 64-bit Python 3.11, then run ./start.sh again." >&2
exit 1
