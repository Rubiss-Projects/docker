# Loaded by E:\Scripts\docker-desktop-common.ps1. Uses its WSL command and logger.
$DockerGrafanaMaintenanceIdPath = 'E:\Scripts\Logs\docker-grafana-maintenance.id'

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
    Set-Content -Path $DockerGrafanaMaintenanceIdPath -Value $token
    Write-DockerLog "Created Sunday Edge Grafana maintenance for $TtlMinutes minutes plus restart grace."
    return $true
}

function Stop-GrafanaMaintenance {
    if (-not (Test-Path $DockerGrafanaMaintenanceIdPath)) { return }
    $token = (Get-Content -Path $DockerGrafanaMaintenanceIdPath | Select-Object -First 1).Trim()
    if ($token -notmatch '^[0-9a-f-]{36}:[0-9a-f-]{36}$') {
        Write-DockerLog 'Invalid Grafana maintenance token; silences will expire automatically.'
        return
    }
    $command = "cd /mnt/e/Docker && python3 scripts/grafana-maintenance.py stop $token"
    $result = Invoke-WslCommand -Command $command -TimeoutSeconds 75 -MaxAttempts 1
    if ($result.ExitCode -eq 0) {
        Remove-Item -Path $DockerGrafanaMaintenanceIdPath -Force
        Write-DockerLog 'Grafana availability maintenance ended; restart notifications resume in 35 minutes.'
    } else {
        Write-DockerLog 'Unable to end Grafana maintenance; silences will expire automatically.'
    }
}
