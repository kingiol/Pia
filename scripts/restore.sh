#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
if [ "$#" -ne 1 ]; then
  echo "usage: $0 BACKUP_PATH (.zip package or .sqlite3)" >&2
  exit 2
fi
"$PWD/scripts/python.sh" -m pia_runtime.cli restore "$1"
