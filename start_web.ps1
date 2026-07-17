$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "port_utils.ps1")

$live = Find-LiveServiceInstance -ServiceId "transcript" -ServiceName "video_transcript" -DefaultPort 8799 -MaxTries 15
if ($null -eq $live) {
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Root\start_api.ps1`""
    Start-Sleep -Seconds 3
    $live = Find-LiveServiceInstance -ServiceId "transcript" -ServiceName "video_transcript" -DefaultPort 8799 -MaxTries 15
}
$base = if ($live) { $live.BaseUrl } else { "http://127.0.0.1:8799" }
Start-Process "$base/ui"
