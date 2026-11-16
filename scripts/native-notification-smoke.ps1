$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = $env:PIA_PYTHON
if (-not $python) {
  $venvPython = Join-Path $root ".venv\Scripts\python.exe"
  $python = if (Test-Path $venvPython) { $venvPython } else { "python" }
}

$env:PYTHONPATH = Join-Path $root "packages-py\pia_runtime"
& $python -c @'
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
}))
if receipt.status != "DELIVERED":
    raise SystemExit(f"native notification smoke failed: {receipt.status}")
'@
