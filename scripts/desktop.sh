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

if [ "${PIA_MANAGED_RUNTIME:-1}" != "0" ]; then
  if ! find "$PWD/apps/desktop/src-tauri/binaries" -maxdepth 1 -type f -name 'pia-runtime-*' -print -quit 2>/dev/null | grep -q .; then
    "$PWD/scripts/build-sidecar.sh"
  fi
fi

cd apps/desktop/src-tauri
if [ "${PIA_MANAGED_RUNTIME:-1}" = "0" ]; then
  exec cargo tauri dev --config '{"bundle":{"externalBin":[]}}'
fi
exec cargo tauri dev
