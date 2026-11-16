$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = $env:PIA_PYTHON
if (-not $python) {
  $venvPython = Join-Path $root ".venv\Scripts\python.exe"
  $python = if (Test-Path $venvPython) { $venvPython } else { "python" }
}

$target = $env:PIA_SIDECAR_TARGET
if (-not $target) {
  $target = ((rustc -Vv | Select-String "^host:").ToString() -split "\s+", 2)[1]
}
if (-not $target) {
  throw "Unable to determine the Rust target triple."
}

& $python -m PyInstaller `
  --clean `
  --noconfirm `
  --distpath (Join-Path $root ".sidecar-dist") `
  --workpath (Join-Path $root ".sidecar-build") `
  (Join-Path $root "sidecar.spec")

$suffix = if ($target -like "*windows*") { ".exe" } else { "" }
$source = Join-Path $root ".sidecar-dist\pia-runtime$suffix"
$destinationDir = Join-Path $root "apps\desktop\src-tauri\binaries"
$destination = Join-Path $destinationDir "pia-runtime-$target$suffix"

New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
Copy-Item -Force $source $destination
Write-Output "Built $destination"
