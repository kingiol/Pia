#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$(uname -s)" != "Darwin" ]; then
  echo "DESKTOP LIFECYCLE SKIP (requires macOS)"
  exit 0
fi

app="${PIA_DESKTOP_APP:-$PWD/apps/desktop/src-tauri/target/release/bundle/macos/Pia.app}"
if [ ! -d "$app" ]; then
  echo "DESKTOP LIFECYCLE FAIL: app not found at $app" >&2
  exit 2
fi

binary="$app/Contents/MacOS/pia-desktop"
sidecar="$app/Contents/MacOS/pia-runtime"
expect_local="${PIA_EXPECT_LOCAL_RUNTIME:-0}"
open -n "$app"

running() {
  pgrep -f "$1" >/dev/null 2>&1
}

for _ in $(seq 1 30); do
  if running "$binary" && { [ "$expect_local" != "1" ] || running "$sidecar"; }; then
    break
  fi
  sleep 0.5
done

if ! running "$binary" || { [ "$expect_local" = "1" ] && ! running "$sidecar"; }; then
  echo "DESKTOP LIFECYCLE FAIL: app or expected local sidecar did not start" >&2
  pkill -f "$sidecar" >/dev/null 2>&1 || true
  exit 2
fi

osascript -e 'tell application "Pia" to quit' >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  if ! running "$binary" && ! running "$sidecar"; then
    echo "DESKTOP LIFECYCLE PASS"
    exit 0
  fi
  sleep 0.5
done

echo "DESKTOP LIFECYCLE FAIL: app left a process behind" >&2
pkill -f "$sidecar" >/dev/null 2>&1 || true
pkill -f "$binary" >/dev/null 2>&1 || true
exit 2
