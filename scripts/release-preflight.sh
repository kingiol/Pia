#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
exec "$PWD/scripts/python.sh" "$PWD/scripts/release_preflight.py" "$@"
