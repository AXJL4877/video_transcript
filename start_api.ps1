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

# ---------------- Auto-start downstream deps (download / asr) ----------------
# video_transcript is an orchestration module: it needs the download + asr
# local services. Probe them and auto-start if missing so the user only has to
# launch this one module. Runs before the "already running" check below so deps
# are ensured even when this service is already up.

function Resolve-ModuleDir {
    param([string]$FolderName)
    $candidates = @(
        (Join-Path (Join-Path $Root "..") $FolderName),
        (Join-Path $env:USERPROFILE "Desktop\mo_kuai\$FolderName"),
        (Join-Path $env:USERPROFILE "Desktop\$FolderName"),
        "D:\Desktop\mo_kuai\$FolderName",
        "D:\Desktop\$FolderName"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path }
    }
    return $null
}

function Start-Downstream {
    param(
        [string]$ServiceId, [string]$ServiceName, [int]$DefaultPort,
        [string]$FolderName, [string[]]$StartScripts
    )
    $live = Find-LiveServiceInstance -ServiceId $ServiceId -ServiceName $ServiceName -DefaultPort $DefaultPort -MaxTries 15
    if ($null -ne $live) {
        Write-Host ">> dependency online: $ServiceName $($live.BaseUrl)"
        return
    }
    $dir = Resolve-ModuleDir $FolderName
    if (-not $dir) {
        Write-Host ">> [warn] folder '$FolderName' not found; cannot auto-start $ServiceName, please start it manually."
        return
    }
    $script = $null
    foreach ($s in $StartScripts) {
        $p = Join-Path $dir $s
        if (Test-Path $p) { $script = $p; break }
    }
    if (-not $script) {
        Write-Host ">> [warn] no start script in '$FolderName'; please start $ServiceName manually."
        return
    }
    Write-Host ">> auto-starting dependency: $ServiceName -> $script"
    if ($script.ToLower().EndsWith(".ps1")) {
        Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $dir | Out-Null
    } else {
        Start-Process cmd -ArgumentList "/c `"$script`"" -WorkingDirectory $dir | Out-Null
    }
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 2
        $live = Find-LiveServiceInstance -ServiceId $ServiceId -ServiceName $ServiceName -DefaultPort $DefaultPort -MaxTries 15
        if ($null -ne $live) {
            Write-Host ">> $ServiceName ready: $($live.BaseUrl)"
            return
        }
    }
    Write-Host ">> [warn] timed out waiting for $ServiceName (first run may be installing deps); retry the task later."
}

Write-Host ">> Checking / auto-starting downstream deps (download / asr) ..."
Start-Downstream -ServiceId "download" -ServiceName "video_download" -DefaultPort 8789 -FolderName "video_download" -StartScripts @("start.bat", "start_web.bat")
Start-Downstream -ServiceId "asr" -ServiceName "audio_asr" -DefaultPort 8791 -FolderName "audio_asr" -StartScripts @("start_api.bat", "start_api.ps1")

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
Write-Host ">> Depends on: download service (:8789) + asr service (:8791) (auto-started by this script)"

& $venvPy -m uvicorn server:app --host $hostAddr --port $port
