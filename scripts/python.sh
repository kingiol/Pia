#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
if [ -n "${PIA_PYTHON:-}" ]; then
  exec "$PIA_PYTHON" "$@"
fi
if [ -x "$root/.venv/bin/python" ]; then
  exec "$root/.venv/bin/python" "$@"
fi
exec python3 "$@"
