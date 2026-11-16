$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$sidecar = Get-ChildItem "apps\desktop\src-tauri\binaries" -Filter "pia-runtime-*.exe" |
  Select-Object -First 1
if (-not $sidecar) {
  throw "Windows sidecar was not produced."
}

$health = (& $sidecar.FullName health --json | ConvertFrom-Json)
if ($health.status -ne "ok") {
  throw "Unexpected sidecar status: $($health.status)"
}
Write-Output "SIDECAR HEALTH PASS"

$desktopBinary = Join-Path $root "apps\desktop\src-tauri\target\release\pia-desktop.exe"
if (-not (Test-Path $desktopBinary)) {
  throw "Windows desktop binary was not produced."
}
$desktopProcess = Start-Process -FilePath $desktopBinary -WorkingDirectory $root -PassThru
try {
  Start-Sleep -Seconds 5
  if ($desktopProcess.HasExited) {
    throw "Windows desktop process exited during startup."
  }
} finally {
  if ($desktopProcess -and -not $desktopProcess.HasExited) {
    Stop-Process -Id $desktopProcess.Id -Force
  }
  $desktopProcess.WaitForExit(10000)
  Start-Sleep -Seconds 2
}
$remainingSidecars = Get-Process pia-runtime -ErrorAction SilentlyContinue
if ($remainingSidecars) {
  $remainingSidecars | Stop-Process -Force
  throw "Windows desktop left a sidecar process behind."
}
Write-Output "DESKTOP LIFECYCLE PASS"

$port = if ($env:PIA_WINDOWS_ACCEPTANCE_PORT) {
  [int]$env:PIA_WINDOWS_ACCEPTANCE_PORT
} else {
  8890
}
$tempRoot = Join-Path $env:TEMP ("pia-windows-acceptance-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$stdout = Join-Path $tempRoot "server.stdout.log"
$stderr = Join-Path $tempRoot "server.stderr.log"
$env:PIA_PORT = "$port"
$env:PIA_DB_PATH = Join-Path $tempRoot "pia.sqlite3"
$env:PIA_DUCKDB_PATH = Join-Path $tempRoot "pia.duckdb"
$env:PIA_AUTOSTART_TASKS = "1"

$process = $null
try {
  $process = Start-Process `
    -FilePath $sidecar.FullName `
    -ArgumentList "serve" `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

  $baseUrl = "http://127.0.0.1:$port/api"
  $ready = $false
  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    try {
      $healthResponse = Invoke-RestMethod -Uri "$baseUrl/health" -Method Get -TimeoutSec 2
      if ($healthResponse.status -eq "ok") {
        $ready = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 250
    }
  }
  if (-not $ready) {
    throw "Packaged sidecar HTTP health did not become ready."
  }

  $taskBody = @{
    trigger_type = "MarketClose"
    target = @{ as_of = "2026-11-05" }
    fixture = @{
      market = "close-2026-11-05.json"
      portfolio = "default.json"
    }
  } | ConvertTo-Json -Depth 5
  $taskResponse = Invoke-RestMethod `
    -Uri "$baseUrl/tasks" `
    -Method Post `
    -ContentType "application/json" `
    -Body $taskBody
  $taskId = $taskResponse.task.id
  $terminal = @("BLOCKED", "NO_ACTION", "WAITING_APPROVAL", "FAILED", "RETRYABLE")
  $detail = $null
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    $detail = Invoke-RestMethod -Uri "$baseUrl/tasks/$taskId" -Method Get
    if ($terminal -contains $detail.task.status) {
      break
    }
    Start-Sleep -Milliseconds 250
  }
  if (-not $detail -or $terminal -notcontains $detail.task.status) {
    throw "Packaged task did not reach a terminal acceptance state."
  }
  if (-not $detail.evidence -or $detail.evidence.Count -lt 3) {
    throw "Packaged task did not persist the expected evidence set."
  }
  Write-Output "TASK E2E PASS $taskId"

  $deviceBody = @{
    device_id = "windows-acceptance-device"
    platform = "windows"
    device_name = "Windows acceptance"
  } | ConvertTo-Json
  Invoke-RestMethod `
    -Uri "$baseUrl/devices" `
    -Method Post `
    -ContentType "application/json" `
    -Body $deviceBody | Out-Null
  Invoke-RestMethod `
    -Uri "$baseUrl/devices/windows-acceptance-device" `
    -Method Delete | Out-Null
  Write-Output "DEVICE LIFECYCLE PASS"
} finally {
  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
  }
  Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue
}

Write-Output "WINDOWS ACCEPTANCE PASS"
