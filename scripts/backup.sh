#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
destination="${1:-.pia/backups/pia-$(date -u +%Y%m%dT%H%M%SZ).zip}"
"$PWD/scripts/python.sh" -m pia_runtime.cli backup "$destination"
