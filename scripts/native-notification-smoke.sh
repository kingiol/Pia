#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This smoke command is for macOS. Use scripts/native-notification-smoke.ps1 on Windows." >&2
  exit 2
fi

"$PWD/scripts/python.sh" - <<'PY'
import json

from pia_runtime.notifications import LocalNotificationProvider

receipt = LocalNotificationProvider(enabled=True).deliver(
    "Pia notification smoke",
    "Native notification delivery is enabled for this desktop.",
    user_id="default",
    notification_id="native-smoke",
)
print(json.dumps({
    "status": receipt.status,
    "provider_id": receipt.provider_id,
    "detail": receipt.detail,
}, ensure_ascii=False))
if receipt.status != "DELIVERED":
    raise SystemExit(f"native notification smoke failed: {receipt.status}")
PY
