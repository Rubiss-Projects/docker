# Loaded by E:\Scripts\docker-desktop-common.ps1. Uses its WSL command and logger.
$DockerGrafanaMaintenanceIdPath = 'E:\Scripts\Logs\docker-grafana-maintenance.id'

function Set-DockerMaintenanceTokens {
    param ([string]$Path, [string[]]$Tokens)
    if ($Tokens.Count -eq 0) {
        Remove-Item -LiteralPath $Path -ErrorAction SilentlyContinue
        return
    }
    $temporary = $Path + ".$PID.tmp"
    try {
        $Tokens | Set-Content -LiteralPath $temporary -ErrorAction Stop
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $Path) }
    } finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
}

function Add-DockerMaintenanceToken {
    param ([string]$Path, [string]$Token)
    $tokens = @()
    if (Test-Path -LiteralPath $Path) { $tokens = @(Get-Content -LiteralPath $Path -ErrorAction Stop) }
    Set-DockerMaintenanceTokens -Path $Path -Tokens @((@($tokens) + $Token) | Sort-Object -Unique)
}

function Start-GrafanaMaintenance {
    param ([int]$TtlMinutes = 30, [string]$Reason = 'planned-docker-restart')

    # Reasons are fixed identifiers from the scheduled tasks, passed to a shell.
    if ($Reason -notmatch '^[a-zA-Z0-9_-]+$' -or $TtlMinutes -le 0) {
        Write-DockerLog 'Invalid Grafana maintenance arguments.'
        return $false
    }
    $command = "cd /mnt/e/Docker && python3 scripts/grafana-maintenance.py start --ttl-minutes $TtlMinutes --reason $Reason all"
    $result = Invoke-WslCommand -Command $command -TimeoutSeconds 75 -MaxAttempts 1
    $token = ($result.Output -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^[0-9a-f-]{36}:[0-9a-f-]{36}$' } | Select-Object -Last 1)
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        Write-DockerLog 'Grafana is unavailable for maintenance setup; retaining nightly mute fallback and continuing Docker recovery.'
        return $false
    }
    try { Add-DockerMaintenanceToken -Path $DockerGrafanaMaintenanceIdPath -Token $token }
    catch {
        try { Invoke-WslCommand -Command "cd /mnt/e/Docker && python3 scripts/grafana-maintenance.py stop $token" -TimeoutSeconds 75 -MaxAttempts 1 | Out-Null } catch { }
        Write-DockerLog 'Could not save Grafana maintenance IDs; immediate cleanup attempted, TTL remains the fallback.'
        return $false
    }
    Write-DockerLog "Created Sunday Edge Grafana maintenance for $TtlMinutes minutes plus restart grace."
    return $true
}

function Stop-GrafanaMaintenance {
    if (-not (Test-Path $DockerGrafanaMaintenanceIdPath)) { return $true }
    $remaining = @()
    foreach ($token in @(Get-Content -LiteralPath $DockerGrafanaMaintenanceIdPath -ErrorAction Stop)) {
        if ($token -notmatch '^[0-9a-f-]{36}:[0-9a-f-]{36}$') { continue }
        $command = "cd /mnt/e/Docker && python3 scripts/grafana-maintenance.py stop $token"
        $result = Invoke-WslCommand -Command $command -TimeoutSeconds 75 -MaxAttempts 1
        if ($result.ExitCode -eq 0) {
            Write-DockerLog 'Grafana availability maintenance ended; restart notifications resume in 35 minutes.'
        } else {
            $remaining += $token
            Write-DockerLog 'Unable to end Grafana maintenance; retaining its IDs for cleanup.'
        }
    }
    Set-DockerMaintenanceTokens -Path $DockerGrafanaMaintenanceIdPath -Tokens $remaining
    return ($remaining.Count -eq 0)
}
