#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "-- iOS transport and push-token contract"
swift test --package-path apps/ios/PiaMobileClient
swift build --package-path apps/ios/PiaMobileClient --product PiaApp

echo "-- Android transport, token store and background worker build"
android_sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$android_sdk" ] && [ -d "${HOME}/Library/Android/sdk" ]; then
  android_sdk="${HOME}/Library/Android/sdk"
elif [ -z "$android_sdk" ] && [ -d "${HOME}/Android/Sdk" ]; then
  android_sdk="${HOME}/Android/Sdk"
fi
if [ -n "$android_sdk" ] && [ -d "$android_sdk" ] && [ -x "./apps/android/gradlew" ]; then
  ANDROID_HOME="$android_sdk" \
  ANDROID_SDK_ROOT="$android_sdk" \
    ./apps/android/gradlew --no-daemon --project-dir apps/android :app:assembleDebug
else
  echo "ANDROID ACCEPTANCE SKIP (Android SDK not found)"
fi

echo "-- Web Push service worker syntax"
node --check apps/web/public/sw.js
test -f apps/web/public/icon.svg
python3 - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("apps/web/public/manifest.webmanifest").read_text())
assert any(icon.get("src") == "/icon.svg" for icon in manifest.get("icons", []))
PY

echo "MOBILE ACCEPTANCE PASS"
