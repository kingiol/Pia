#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
output="${PIA_RELEASE_MANIFEST:-.pia/release/manifest.json}"
signature="${PIA_RELEASE_SIGNATURE:-.pia/release/manifest.sig}"
artifacts=()

for path in \
  apps/desktop/src-tauri/target/release/bundle/macos \
  apps/desktop/src-tauri/target/release/bundle/dmg \
  apps/desktop/src-tauri/target/release/bundle/msi \
  apps/desktop/src-tauri/binaries \
  apps/android/app/build/outputs/apk
do
  if [ -e "$path" ]; then
    artifacts+=("$path")
  fi
done

if [ "${#artifacts[@]}" -eq 0 ]; then
  echo "No release artifacts found." >&2
  exit 2
fi

args=(
  scripts/release_manifest.py
  --root "$PWD"
  --output "$output"
)
if [ -n "${PIA_RELEASE_SIGNING_KEY:-}" ]; then
  args+=(--sign-key "$PIA_RELEASE_SIGNING_KEY" --signature-output "$signature")
fi
args+=("${artifacts[@]}")
"$PWD/scripts/python.sh" "${args[@]}"
