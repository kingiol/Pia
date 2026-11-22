#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! cargo tauri --version >/dev/null 2>&1; then
  echo "cargo-tauri is not installed."
  echo "Install it once with: cargo install tauri-cli --version '^2'"
  exit 1
fi

export PYTHONPATH="$PWD/packages-py/pia_runtime"
export PIA_RUNTIME_ROOT="$PWD"
export PIA_DATA_PROVIDER="${PIA_DATA_PROVIDER:-akshare}"
if [ -z "${PIA_PYTHON:-}" ] && [ -x "$PWD/.venv/bin/python" ]; then
  export PIA_PYTHON="$PWD/.venv/bin/python"
fi

cd apps/desktop/src-tauri
exec cargo tauri dev --config tauri.debug.conf.json --config '{"bundle":{"externalBin":[]}}'
