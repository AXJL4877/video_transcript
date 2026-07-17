# Port probing and registry write (%USERPROFILE%\.scene-studio\ports.json)

function Get-AdvertiseHost {
    param([string]$HostAddr)
    if ([string]::IsNullOrWhiteSpace($HostAddr) -or $HostAddr -eq "0.0.0.0" -or $HostAddr -eq "::") {
        return "127.0.0.1"
    }
    return $HostAddr
}

function Test-PortFree {
    param([string]$HostAddr = "127.0.0.1", [int]$Port)
    $probeHost = Get-AdvertiseHost $HostAddr
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Parse($probeHost), $Port)
        $listener.Start()
    } catch {
        return $false
    } finally {
        if ($listener) { try { $listener.Stop() } catch {} }
    }
    return $true
}

function Find-FreePort {
    param(
        [string]$HostAddr = "127.0.0.1",
        [int]$StartPort = 8799,
        [int]$MaxTries = 15
    )
    for ($i = 0; $i -lt $MaxTries; $i++) {
        $p = $StartPort + $i
        if (Test-PortFree -HostAddr $HostAddr -Port $p) { return $p }
    }
    throw "Ports $StartPort to $($StartPort + $MaxTries - 1) are all in use"
}

function Read-PortRegistryJson {
    $file = Join-Path $env:USERPROFILE ".scene-studio\ports.json"
    if (-not (Test-Path $file)) { return "{}" }
    try {
        return Get-Content $file -Raw -Encoding UTF8
    } catch {
        return "{}"
    }
}

function Write-ServicePortRegistry {
    param(
        [string]$ServiceId,
        [string]$HostAddr,
        [int]$Port,
        [string]$ServiceName,
        [int]$DefaultPort = 8799,
        [int]$ProcessId = 0
    )
    $dir = Join-Path $env:USERPROFILE ".scene-studio"
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $file = Join-Path $dir "ports.json"
    $raw = Read-PortRegistryJson
    if ([string]::IsNullOrWhiteSpace($raw)) { $raw = "{}" }

    $pubHost = Get-AdvertiseHost $HostAddr
    $pidVal = if ($ProcessId -gt 0) { $ProcessId } else { $PID }
    $entry = @{
        service     = $ServiceName
        serviceId   = $ServiceId
        host        = $pubHost
        bindHost    = $HostAddr
        port        = $Port
        defaultPort = $DefaultPort
        baseUrl     = "http://${pubHost}:${Port}"
        pid         = $pidVal
        updatedAt   = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    }
    $entryJson = ($entry | ConvertTo-Json -Compress)
    $serviceKey = '"' + $ServiceId + '"'

    if ($raw -match [regex]::Escape($serviceKey)) {
        $pattern = '(?s)"' + [regex]::Escape($ServiceId) + '"\s*:\s*\{.*?\}'
        $raw = [regex]::Replace($raw, $pattern, ('"' + $ServiceId + '": ' + $entryJson), 1)
    } elseif ($raw.Trim() -eq "{}") {
        $raw = "{`n  `"$ServiceId`": $entryJson`n}"
    } else {
        $trim = $raw.TrimEnd()
        if ($trim.EndsWith("}")) {
            $trim = $trim.Substring(0, $trim.Length - 1)
            $raw = $trim + ",`n  `"$ServiceId`": $entryJson`n}"
        }
    }

    [System.IO.File]::WriteAllText($file, $raw, (New-Object System.Text.UTF8Encoding $false))
}

function Test-ServiceHealth {
    param(
        [string]$HostAddr = "127.0.0.1",
        [int]$Port,
        [string]$ExpectedService = "video_transcript",
        [int]$TimeoutSec = 2
    )
    $pub = Get-AdvertiseHost $HostAddr
    try {
        $resp = Invoke-WebRequest -Uri "http://${pub}:${Port}/health" -UseBasicParsing -TimeoutSec $TimeoutSec
        if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) { return $null }
        $data = $resp.Content | ConvertFrom-Json
        if ($ExpectedService -and $data.service -and ($data.service -ne $ExpectedService)) {
            return $null
        }
        return $data
    } catch {
        return $null
    }
}

function Find-LiveServiceInstance {
    param(
        [string]$ServiceId = "transcript",
        [string]$ServiceName = "video_transcript",
        [int]$DefaultPort = 8799,
        [int]$MaxTries = 15
    )
    $candidates = New-Object System.Collections.Generic.List[int]
    $registry = Join-Path $env:USERPROFILE ".scene-studio\ports.json"
    if (Test-Path $registry) {
        try {
            $json = Get-Content $registry -Raw -Encoding UTF8 | ConvertFrom-Json
            $node = $json.$ServiceId
            if ($node -and $node.port) { [void]$candidates.Add([int]$node.port) }
        } catch {}
    }
    for ($i = 0; $i -lt $MaxTries; $i++) {
        $p = $DefaultPort + $i
        if (-not $candidates.Contains($p)) { [void]$candidates.Add($p) }
    }
    foreach ($p in $candidates) {
        $health = Test-ServiceHealth -Port $p -ExpectedService $ServiceName
        if ($null -ne $health) {
            $pidFromHealth = 0
            if ($health.pid) { $pidFromHealth = [int]$health.pid }
            Write-ServicePortRegistry -ServiceId $ServiceId -HostAddr "127.0.0.1" -Port $p `
                -ServiceName $ServiceName -DefaultPort $DefaultPort -ProcessId $pidFromHealth
            return @{
                Port    = $p
                BaseUrl = "http://127.0.0.1:${p}"
                Health  = $health
            }
        }
    }
    return $null
}

function Resolve-TranscriptPort {
    param([string]$HostAddr = "127.0.0.1")
    $preferred = 8799
    if ($env:TRANSCRIPT_PORT) {
        $forced = [int]$env:TRANSCRIPT_PORT
        if (Test-PortFree -HostAddr $HostAddr -Port $forced) { return $forced }
        Write-Host ">> Requested port $forced is busy, finding a free port..."
    }
    $registry = Join-Path $env:USERPROFILE ".scene-studio\ports.json"
    if (Test-Path $registry) {
        try {
            $json = Get-Content $registry -Raw -Encoding UTF8 | ConvertFrom-Json
            $node = $json.'transcript'
            if ($node -and $node.port) {
                $regPort = [int]$node.port
                if (Test-PortFree -HostAddr $HostAddr -Port $regPort) { return $regPort }
            }
        } catch {}
    }
    return Find-FreePort -HostAddr $HostAddr -StartPort $preferred
}
