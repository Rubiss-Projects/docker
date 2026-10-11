param ([switch]$ValidateOnly)

# Scheduled every minute. Control-plane errors alone never authorize disruption.

$logFilePath = "E:\Scripts\Logs\docker-desktop-logs.txt"
$commonScriptPath = Join-Path $PSScriptRoot 'docker-desktop-common.ps1'
$maxRestartAttempts = 3
$restartCooldownMinutes = 10
$restartWindowMinutes = 60

# Kept outside Git by the installer; never include the URL in diagnostic output.
$discordWebhookUrl = ''
$notificationPath = Join-Path $PSScriptRoot 'docker-watchdog-notifications.json'

function Get-DockerNotificationWebhook {
    param ([string]$Path)
    try {
        if (-not (Test-Path -LiteralPath $Path)) { return '' }
        $settings = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        return [string]$settings.DiscordWebhookUrl
    } catch {
        Write-Log 'Notification settings could not be loaded; continuing watchdog checks without notifications.'
        return ''
    }
}

function Test-MaintenanceWindow {
    if (Test-Path $DockerMaintenanceLockPath) {
        if (-not $script:DockerOperationLock) { return $true }
        # Both entry points now hold the same exclusive operation lock. If the
        # watchdog owns it, a leftover nightly marker has no active owner.
        Write-Log 'Removing an orphaned nightly maintenance marker while holding the operation lock.'
        Remove-Item -Path $DockerMaintenanceLockPath -Force -ErrorAction Stop
    }

    return $false
}

function Write-Log {
    param ([string]$message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "$timestamp - $message"
    Add-Content -Path $logFilePath -Value $logMessage
    Write-Host $logMessage
}

function Send-DiscordAlert {
    param (
        [string]$title,
        [string]$description,
        [string]$color = "15158332"
    )

    if ([string]::IsNullOrWhiteSpace($discordWebhookUrl)) {
        Write-Log 'No watchdog notification URL configured.'
        return
    }
    try {
        $payload = @{
            embeds = @(
                @{
                    title = $title
                    description = $description
                    color = [int]$color
                    timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
                    footer = @{
                        text = "Docker Health Monitor"
                    }
                }
            )
        } | ConvertTo-Json -Depth 4 -Compress

        $response = Invoke-RestMethod -Uri $discordWebhookUrl -Method Post -Body $payload -ContentType "application/json"
        Write-Log "Discord alert sent successfully: $title"
    } catch {
        Write-Log 'Failed to send Discord alert; notification credentials are omitted.'
    }
}

function Clean-LogFile {
    if (Test-Path $logFilePath) {
        try {
            $cutoffDate = (Get-Date).AddDays(-7)
            $logContent = Get-Content $logFilePath
            $filteredContent = $logContent | Where-Object {
                if ($_ -match '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}') {
                    $timestampString = $_.Substring(0, 19)
                    try {
                        $logTimestamp = [DateTime]::ParseExact($timestampString, "yyyy-MM-dd HH:mm:ss", $null)
                        return $logTimestamp -ge $cutoffDate
                    } catch {
                        return $true
                    }
                }
                return $true
            }
            if ($filteredContent.Count -lt $logContent.Count) {
                $filteredContent | Set-Content -Path $logFilePath
                Write-Log "Log cleanup completed. Removed entries older than 7 days."
            }
        } catch {
            Write-Log "Warning: Could not clean log file: $($_.Exception.Message)"
        }
    }
}

function Enter-HealthMonitorLock {
    return Enter-DockerOperationLock -WaitSeconds 20
}

function Exit-HealthMonitorLock {
    Exit-DockerOperationLock
}

function Repair-ConfirmedDockerServiceHealth {
    param ([Parameter(Mandatory = $true)]$Health)
    if (-not $Health.Confirmed) { return $false }
    if ($Health.Kind -eq 'CriticalService') {
        Write-Log 'Critical service failure persisted; attempting ordered service repair.'
        return Start-CriticalDockerServices -TimeoutSeconds 480
    }
    if ($Health.Kind -eq 'Sentinel' -and $Health.FailedServices.Count -gt 0) {
        Write-Log "Confirmed sentinel failures; repairing only: $($Health.FailedServices -join ', ')."
        return Repair-WslComposeBindServices -ServiceNames $Health.FailedServices -OnlySpecified
    }
    return $false
}

function Restart-DockerDesktop {
    param ([switch]$ResumeOnly)
    if ($ResumeOnly) { Write-Log '=== RESUMING DOCKER SERVICE RECOVERY ===' }
    else { Write-Log "=== RESTARTING DOCKER DESKTOP ===" }
    $runningWslComposeServices = @()
    if (Test-Path -LiteralPath $DockerRecoveryInventoryPath) {
        $runningWslComposeServices = @(Get-DockerRecoveryInventory)
    } else {
        try {
            $runningWslComposeServices = @(Get-RunningWslComposeServiceNames)
            Save-DockerRecoveryInventory -ServiceNames $runningWslComposeServices
            Write-Log "Captured $($runningWslComposeServices.Count) running WSL compose service(s) through the Windows Docker CLI."
        } catch {
            try {
                if (-not (Test-Path -LiteralPath $DockerHealthyInventoryPath)) { throw 'No healthy inventory snapshot exists.' }
                $runningWslComposeServices = @(Get-DockerRecoveryInventory -Path $DockerHealthyInventoryPath -RequireRecent)
                Save-DockerRecoveryInventory -ServiceNames $runningWslComposeServices
                Write-Log "Live inventory unavailable; preserving $($runningWslComposeServices.Count) projects from the last healthy observation."
            } catch {
                Write-Log 'Recovery withheld: neither live nor saved healthy service inventory is available.'
                return $false
            }
        }
    }

    $maintenanceStarted = Start-UptimeKumaMaintenance -Reason 'watchdog-docker-recovery'
    try {
        if (-not $ResumeOnly -and -not (Restart-DockerDesktopClean -TimeoutSeconds 600 -ShutdownWslOnFallback)) {
            Write-Log 'Docker Desktop restart did not reach daemon readiness.'
            return $false
        }
        if (-not (Start-CriticalDockerServices -TimeoutSeconds 480)) { return $false }
        if (-not $maintenanceStarted) {
            $maintenanceStarted = Start-UptimeKumaMaintenance -Reason 'watchdog-bind-recovery'
        }
        # A saved journal is not evidence that every stack is broken. Check its
        # containers and mounts before recreating anything on a resumed attempt.
        if ($ResumeOnly) {
            $targets = Get-DockerPendingRecoveryTargets -ServiceNames $runningWslComposeServices
            if (-not $targets.Valid) { return $false }
            $runningWslComposeServices = @($targets.Services)
        }
        if (-not (Repair-WslComposeBindServices -ServiceNames $runningWslComposeServices -TimeoutSeconds 1200 -OnlySpecified:$ResumeOnly)) {
            Write-Log 'Docker Desktop restarted, but WSL compose bind repair failed.'
            return $false
        }
        if (-not $ResumeOnly -or -not (Test-DockerContainerReady -Name 'cadvisor' -Quiet)) {
            if (-not (Repair-WindowsComposeServices -ServiceNames @('cadvisor'))) { return $false }
        }
        if (-not (Start-CriticalDockerServices -TimeoutSeconds 480)) { return $false }
        if ((Get-ConfirmedDockerHealth).Kind -ne 'Healthy') {
            Write-Log 'Docker Desktop restarted, but final health checks failed.'
            return $false
        }
        Write-Log 'Docker Desktop restarted successfully and critical services are functional.'
        Remove-Item -LiteralPath $DockerRecoveryInventoryPath -Force -ErrorAction SilentlyContinue
        return $true
    } finally {
        if ($maintenanceStarted) { Stop-UptimeKumaMaintenance | Out-Null }
    }
}

function Test-DockerRestartAllowed {
    $now = Get-Date
    $restartTimes = @(Get-Content $logFilePath -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_ -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - === RESTARTING DOCKER DESKTOP ===') {
            [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
        }
    })
    $recent = @($restartTimes | Where-Object { $_ -gt $now.AddMinutes(-$restartWindowMinutes) })
    if ($recent.Count -ge $maxRestartAttempts) {
        Write-Log "Restart limit reached: $maxRestartAttempts attempts in $restartWindowMinutes minutes. Deferring another restart."
        return $false
    }
    if ($restartTimes.Count -gt 0 -and $restartTimes[-1] -gt $now.AddMinutes(-$restartCooldownMinutes)) {
        Write-Log "Docker Desktop restart cooldown is active ($restartCooldownMinutes minutes)."
        return $false
    }
    return $true
}

function Test-DockerServiceRepairAllowed {
    param ([Parameter(Mandatory = $true)]$Health)
    $signature = $Health.Kind + '|' + ($Health.FailedServices -join ',')
    $cutoff = (Get-Date).AddMinutes(-$restartCooldownMinutes)
    foreach ($line in (Get-Content $logFilePath -ErrorAction SilentlyContinue)) {
        if ($line -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - === REPAIRING DOCKER SERVICES === (.+)$') {
            if ($Matches[2] -eq $signature -and [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null) -gt $cutoff) {
                Write-Log "Service repair cooldown is active for $signature."
                return $false
            }
        }
    }
    return $true
}

function Invoke-DockerHealthMonitor {
    Clean-LogFile
    if (Test-MaintenanceWindow) {
        Write-Log 'Skipping watchdog checks during nightly maintenance.'
        return 0
    }
    Write-Log '=== Docker Health Check Started (service-aware watchdog) ==='
    if ((Test-Path -LiteralPath $DockerRecoveryInventoryPath) -and (Test-DockerDaemon) -and (Test-WslDockerIntegration)) {
        # A previous attempt may have rebooted Windows after stopping critical services.
        # Finish that recovery without restarting an engine that is already ready.
        $pendingRecovery = [pscustomobject]@{ Kind = 'Recovery'; FailedServices = @() }
        if (-not (Test-DockerServiceRepairAllowed -Health $pendingRecovery)) { return 1 }
        Write-Log '=== REPAIRING DOCKER SERVICES === Recovery|'
        if (Restart-DockerDesktop -ResumeOnly) { return 0 }
        return 1
    }
    $health = Get-ConfirmedDockerHealth
    if ($health.Kind -eq 'Healthy') {
        try { Save-DockerHealthyInventory }
        catch { Write-Log 'Could not refresh the healthy service inventory; retaining the previous snapshot.' }
        Write-Log 'Docker and critical services are running and functional.'
        return 0
    }
    if (-not $health.Confirmed) {
        Write-Log 'Health failures changed between retries; deferring disruptive recovery until a failure persists.'
        return 1
    }

    if ($health.Kind -in @('CriticalService', 'Sentinel')) {
        if (-not (Test-DockerServiceRepairAllowed -Health $health)) { return 1 }
        Write-Log "=== REPAIRING DOCKER SERVICES === $($health.Kind)|$($health.FailedServices -join ',')"
        $maintenanceStarted = Start-UptimeKumaMaintenance -Reason 'watchdog-service-repair'
        try {
            Repair-ConfirmedDockerServiceHealth -Health $health | Out-Null
            $health = Get-ConfirmedDockerHealth
        } finally {
            if ($maintenanceStarted) { Stop-UptimeKumaMaintenance | Out-Null }
        }
        if ($health.Kind -eq 'Healthy') {
            Write-Log 'Service health recovered without restarting Docker Desktop.'
            return 0
        }
    }

    # Application failures and incomplete probes are not daemon failures.
    if (-not $health.Confirmed -or $health.Kind -notin @('Daemon', 'WslTransport', 'WslIntegration')) {
        Write-Log "Service/probe issue remains ($($health.Kind)); keeping Docker Desktop running. $($health.Detail)"
        return 1
    }
    if (-not (Test-DockerRestartAllowed)) { return 1 }
    if (-not (Test-DockerAutomaticRecoveryAllowed)) {
        Write-Log "Degraded $($health.Kind); broad recovery withheld because user-facing outage was not confirmed."
        return 1
    }
    # The independent probes take time. Do not act on an obsolete control-plane
    # failure if it recovered while we were checking user impact.
    $current = Get-DockerHealthSnapshot
    if ($current.Kind -ne $health.Kind) {
        Write-Log "Recovery deferred: health changed from $($health.Kind) to $($current.Kind)."
        return 1
    }
    Write-Log "Persistent $($health.Kind) failure and broad service outage confirmed; starting Desktop recovery."
    Send-DiscordAlert -title '[WARNING] Docker Desktop Recovery' -description "Persistent $($health.Kind) failure and three independent service-outage checks. Starting automatic recovery." -color '15105570'
    if (Restart-DockerDesktop) {
        Write-Log '=== Docker Health Check Completed Successfully ==='
        Send-DiscordAlert -title '[OK] Docker Desktop Recovered' -description 'Docker Desktop and critical services passed recovery checks.' -color '3066993'
        return 0
    }
    Write-Log '=== Docker Health Check FAILED - Manual intervention may be required ==='
    if ($script:DockerHostRebootRequested) {
        Send-DiscordAlert -title '[WARNING] Windows Recovery Restart' -description 'WSL could not shut down. A controlled Windows reboot is scheduled; Docker service recovery will resume afterward. Automatic host reboots are limited to one per six hours.' -color '15105570'
        return 1
    }
    Send-DiscordAlert -title '[ERROR] Docker Desktop Recovery Failed' -description 'Automatic recovery failed. See E:\Scripts\Logs\docker-desktop-logs.txt.' -color '15158332'
    return 1
}

# === MAIN SCRIPT LOGIC ===

if (-not (Test-Path $commonScriptPath)) { throw "Missing common Docker script: $commonScriptPath" }
. $commonScriptPath
$discordWebhookUrl = Get-DockerNotificationWebhook -Path $notificationPath

if ($ValidateOnly) {
    $health = Get-ConfirmedDockerHealth
    Write-Log "Read-only watchdog validation: $($health.Kind)"
    if ($health.Kind -eq 'Healthy') { exit 0 }
    exit 1
}


$exitCode = 1
if (Enter-HealthMonitorLock) {
    try {
        $exitCode = Invoke-DockerHealthMonitor
        # Native Caddy has independent remediation: never classify it as a Docker failure.
        if ($exitCode -eq 0 -and -not (Test-MaintenanceWindow)) {
            . 'E:\Docker\caddy\watchdog.ps1'
            if (-not (Invoke-CaddyPlexHealth -Repair)) { $exitCode = 1 }
        }
    } finally {
        Exit-HealthMonitorLock
    }
} else {
    $exitCode = 0
}

exit $exitCode
