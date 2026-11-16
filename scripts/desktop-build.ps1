$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (cargo tauri --version 2>$null)) {
  throw "cargo-tauri is not installed. Install it with: cargo install tauri-cli --version '^2'"
}

if (-not (Get-ChildItem (Join-Path $root "apps\desktop\src-tauri\binaries") -Filter "pia-runtime-*" -File -ErrorAction SilentlyContinue)) {
  & (Join-Path $root "scripts\build-sidecar.ps1")
}

Push-Location (Join-Path $root "apps\desktop\src-tauri")
try {
  cargo tauri build
}
finally {
  Pop-Location
}

$sidecar = Get-ChildItem `
  (Join-Path $root "apps\desktop\src-tauri\binaries") `
  -Filter "pia-runtime-*.exe" `
  -File `
  -ErrorAction SilentlyContinue |
  Select-Object -First 1
if (-not $sidecar) {
  throw "Windows sidecar artifact was not produced."
}

$msi = Get-ChildItem `
  (Join-Path $root "apps\desktop\src-tauri\target\release\bundle\msi") `
  -Filter "*.msi" `
  -File `
  -ErrorAction SilentlyContinue |
  Select-Object -First 1
if (-not $msi) {
  throw "Windows MSI artifact was not produced."
}

Write-Output "WINDOWS BUILD PASS $($msi.FullName)"
