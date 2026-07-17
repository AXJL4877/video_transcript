# Start the video_transcript service (auto-fallback when port is busy)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "port_utils.ps1")
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host ">> Creating .venv ..."
    python -m venv .venv
    $venvPy = Join-Path $Root ".venv\Scripts\python.exe"
}

Write-Host ">> Installing dependencies..."
& $venvPy -m pip install -q -r (Join-Path $Root "requirements.txt")

$hostAddr = if ($env:TRANSCRIPT_HOST) { $env:TRANSCRIPT_HOST } else { "0.0.0.0" }

$live = Find-LiveServiceInstance -ServiceId "transcript" -ServiceName "video_transcript" -DefaultPort 8799 -MaxTries 15
if ($null -ne $live) {
    Write-Host ">> video_transcript already running: $($live.BaseUrl)"
    Write-Host ">> ports.json refreshed. Exiting this window."
    exit 0
}

$port = Resolve-TranscriptPort -HostAddr $hostAddr
$env:TRANSCRIPT_PORT = "$port"
$env:TRANSCRIPT_HOST = $hostAddr
Write-ServicePortRegistry -ServiceId "transcript" -HostAddr $hostAddr -Port $port -ServiceName "video_transcript" -DefaultPort 8799

$pub = if ($hostAddr -eq "0.0.0.0") { "127.0.0.1" } else { $hostAddr }
Write-Host ">> Starting API: http://${pub}:$port"
Write-Host ">> Console /ui  - health /health  - docs /docs"
Write-Host ">> Depends on: download service (:8789) + asr service (:8791)"

& $venvPy -m uvicorn server:app --host $hostAddr --port $port
