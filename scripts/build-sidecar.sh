#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python_bin="${PIA_PYTHON:-$PWD/.venv/bin/python}"
if [ ! -x "$python_bin" ]; then
  python_bin="${PYTHON:-python3}"
fi

target="${PIA_SIDECAR_TARGET:-$(rustc -Vv | sed -n 's/^host: //p')}"
if [ -z "$target" ]; then
  echo "Unable to determine the Rust target triple." >&2
  exit 1
fi

"$python_bin" -m PyInstaller \
  --clean \
  --noconfirm \
  --distpath "$PWD/.sidecar-dist" \
  --workpath "$PWD/.sidecar-build" \
  "$PWD/sidecar.spec"

mkdir -p "$PWD/apps/desktop/src-tauri/binaries"
suffix=""
if [[ "$target" == *windows* ]]; then
  suffix=".exe"
fi
output="$PWD/apps/desktop/src-tauri/binaries/pia-runtime-${target}${suffix}"
cp "$PWD/.sidecar-dist/pia-runtime${suffix}" "$output"
chmod +x "$output" 2>/dev/null || true
echo "Built $output"
