$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "port_utils.ps1")

function Start-ApiSilent {
  param([string]$ScriptPath)
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "powershell.exe"
  $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  if ($psi.EnvironmentVariables.ContainsKey("KE_SILENT")) {
    $psi.EnvironmentVariables["KE_SILENT"] = "1"
  } else {
    $psi.EnvironmentVariables.Add("KE_SILENT", "1")
  }
  [void][System.Diagnostics.Process]::Start($psi)
}

$live = Find-LiveServiceInstance -ServiceId "transcript" -ServiceName "video_transcript" -DefaultPort 8799 -MaxTries 15
if ($null -eq $live) {
    Start-ApiSilent -ScriptPath (Join-Path $Root "start_api.ps1")
    Start-Sleep -Seconds 3
    $live = Find-LiveServiceInstance -ServiceId "transcript" -ServiceName "video_transcript" -DefaultPort 8799 -MaxTries 15
}
$base = if ($live) { $live.BaseUrl } else { "http://127.0.0.1:8799" }
Start-Process "$base/ui"
