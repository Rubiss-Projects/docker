# Loaded by test-existing-watchdog.ps1 inside its isolated, non-mutating harness.
function Availability([string]$State = 'Unavailable') {
    foreach ($address in @('127.0.0.1', '192.168.50.40')) {
        foreach ($name in @('channels-dvr', 'plex', 'sonarr', 'radarr')) {
            [pscustomobject]@{ Name = $name; Address = $address; State = $State }
        }
    }
}

Run-Test 'Windows probes are bounded, bypass proxies, and accept authentication responses' {
    Set-Item Function:Get-DockerServiceAvailability $realAvailability
    function Invoke-ProcessWithTimeout {
        param($FilePath, $Arguments, $TimeoutSeconds, [switch]$Quiet)
        Assert-True ($FilePath -like '*System32\curl.exe' -and $TimeoutSeconds -eq 8) 'Wrong probe or missing deadline'
        Assert-True (($Arguments -join ' ') -match '--noproxy \* --connect-timeout 2 --max-time 5') 'Probe may use proxy or hang'
        [pscustomobject]@{ExitCode=0;Output='403'}
    }
    $checks = @(Get-DockerServiceAvailability)
    Assert-True ($checks.Count -eq 8 -and @($checks | Where-Object State -ne Responding).Count -eq 0) '403 misclassified as broad outage'
}
Run-Test 'probe failures differ from service failures' {
    Set-Item Function:Get-DockerServiceAvailability $realAvailability
    foreach ($code in @(7, 28, 52, 55, 56, 2, 124)) {
        $script:probeExit = $code
        function Invoke-ProcessWithTimeout { [pscustomobject]@{ExitCode=$script:probeExit;Output='000'} }
        $expected = if ($code -in @(2, 124)) { 'Unknown' } else { 'Unavailable' }
        Assert-True (@(Get-DockerServiceAvailability | Where-Object State -ne $expected).Count -eq 0) "Wrong classification for exit $code"
    }
    function Invoke-ProcessWithTimeout { throw 'curl missing' }
    Assert-True (@(Get-DockerServiceAvailability | Where-Object State -ne Unknown).Count -eq 0) 'Broken probe authorizes recovery'
}
Run-Test 'partial HTTP reply is inconclusive even when its body times out' {
    Set-Item Function:Get-DockerServiceAvailability $realAvailability
    function Invoke-ProcessWithTimeout { [pscustomobject]@{ExitCode=28;Output='200'} }
    Assert-True (@(Get-DockerServiceAvailability | Where-Object State -ne Unknown).Count -eq 0) 'Partial reply permits disruption'
}
Run-Test 'working LAN Channels protects streams despite failed localhost probes' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Get-DockerServiceAvailability {
        $checks = @(Availability)
        $checks[4].State = 'Responding'
        $checks
    }
    Assert-True (-not (Test-DockerServiceOutage -RetryDelaySeconds 0)) 'Working LAN service did not veto'
}
Run-Test 'all endpoints must fail for three separated observations' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Get-DockerServiceAvailability { $script:calls++; Availability }
    function Start-Sleep { param($Seconds) Assert-True ($Seconds -eq 30) 'Wrong debounce'; $script:events += 'wait' }
    Assert-True (Test-DockerServiceOutage) 'Confirmed broad outage rejected'
    Assert-True ($script:calls -eq 3 -and $script:events.Count -eq 2) 'Confirmation missing'
}
Run-Test 'a recovering endpoint cancels confirmation' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Get-DockerServiceAvailability {
        $script:calls++
        if ($script:calls -eq 3) { Availability Responding } else { Availability }
    }
    Assert-True (-not (Test-DockerServiceOutage -RetryDelaySeconds 0)) 'Recovered endpoint ignored'
}
Run-Test 'unknown and incomplete probe results cannot authorize recovery' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Get-DockerServiceAvailability { Availability Unknown }
    Assert-True (-not (Test-DockerServiceOutage -RetryDelaySeconds 0)) 'Unknown accepted'
    function Get-DockerServiceAvailability { @(Availability)[0] }
    Assert-True (-not (Test-DockerServiceOutage -RetryDelaySeconds 0)) 'Incomplete accepted'
}
Run-Test 'Windows boot grace and unknown boot time withhold recovery' {
    Set-Item Function:Test-DockerAutomaticRecoveryAllowed $realRecoveryAllowed
    function Test-DockerServiceOutage { throw 'Should wait for startup' }
    function Get-CimInstance { [pscustomobject]@{LastBootUpTime=(Get-Date).AddMinutes(-5)} }
    Assert-True (-not (Test-DockerAutomaticRecoveryAllowed)) 'Boot grace ignored'
    function Get-CimInstance { throw 'CIM unavailable' }
    Assert-True (-not (Test-DockerAutomaticRecoveryAllowed)) 'Unknown boot accepted'
    function Get-CimInstance { [pscustomobject]@{LastBootUpTime=(Get-Date).AddMinutes(-11)} }
    function Test-DockerServiceOutage { $true }
    Assert-True (Test-DockerAutomaticRecoveryAllowed) 'Expired grace blocked recovery'
}
Run-Test 'incident replay keeps services running for persistent WSL and API failures' {
    foreach ($kind in @('WslTransport', 'WslIntegration', 'Daemon')) {
        $script:incidentKind = $kind
        function Get-ConfirmedDockerHealth { Health $script:incidentKind }
        function Test-DockerAutomaticRecoveryAllowed { $false }
        function Restart-DockerDesktop { throw 'Restarted working services' }
        Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Degraded state falsely reported healthy'
        Assert-True ($script:events.Count -eq 0) 'Incident sent recovery alerts or changed maintenance'
        Assert-True (-not (Test-Path -LiteralPath $DockerRecoveryInventoryPath)) 'Incident left a recovery journal'
    }
}
Run-Test 'backend recovery during outage checks cancels stale restart decision' {
    function Get-ConfirmedDockerHealth { Health WslTransport }
    function Get-DockerHealthSnapshot { Health }
    function Restart-DockerDesktop { throw 'Acted on stale failure' }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Stale failure accepted'
    Assert-True ($script:events.Count -eq 0) 'Unnecessary recovery notification'
}
Run-Test 'recovered services veto CLI restart, hard stop, WSL shutdown, and host reboot' {
    function Test-DockerServiceOutage { $false }
    function Test-DockerAutomaticRecoveryAllowed { $false }
    function Invoke-DockerCliWithTimeout { throw 'Docker mutation' }
    function Invoke-ProcessWithTimeout { throw 'Host mutation' }
    function Test-CurrentProcessElevated { $true }
    $script:DockerOperationLock = [pscustomobject]@{}
    try {
        Assert-True (-not (Restart-DockerDesktopClean)) 'CLI restart permitted'
        Assert-True (-not (Invoke-DockerDesktopHardRecovery -ShutdownWsl)) 'Hard stop permitted'
        Assert-True (-not (Stop-DockerWslForRecovery)) 'WSL shutdown permitted'
        Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Host reboot permitted'
    } finally { $script:DockerOperationLock = $null }
}
Run-Test 'cold startup gets the full ten-minute readiness budget' {
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=124;Output='timeout'} }
    function Wait-DockerDesktopReady { param($TimeoutSeconds) Assert-True ($TimeoutSeconds -eq 600) 'Readiness capped at three minutes'; $true }
    Assert-True (Restart-DockerDesktopClean -TimeoutSeconds 600) 'Delayed startup rejected'
}
Run-Test 'pending journal only selects stopped projects and confirmed bad mounts' {
    Set-Item Function:Get-DockerPendingRecoveryTargets $realPendingTargets
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$false;ExitCode=1;FailedServices=@('homepage')} }
    function Get-WslComposeContainers {
        foreach ($name in @('channels-dvr','sonarr','transmission','mod-mc')) {
            [pscustomobject]@{Project=$name;Container=($name+'-generated-1');Status=$(if ($name -eq 'sonarr') {'exited'} else {'running'})}
        }
        [pscustomobject]@{Project='mod-mc';Container='mod-mc-init-1';Status='exited'}
    }
    $targets = Get-DockerPendingRecoveryTargets -ServiceNames @('channels-dvr','sonarr','transmission','mod-mc')
    Assert-True ($targets.Valid -and ($targets.Services -join ',') -eq 'homepage,sonarr') 'Recreated working or RPC-busy containers'
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$false;ExitCode=124;FailedServices=@()} }
    Assert-True (-not (Get-DockerPendingRecoveryTargets -ServiceNames @('channels-dvr')).Valid) 'Probe timeout authorized bind repair'
}
Run-Test 'Plex LAN response vetoes loopback-only targeted restart' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Test-ContainerUrl { $true }
    function Test-HostUrl { $false }
    function Get-DockerServiceAvailability {
        param($ServiceNames)
        Assert-True (($ServiceNames -join ',') -eq 'plex') 'Plex repair must check its own endpoints'
        $checks = @(Availability | Where-Object Name -eq plex)
        $checks[1].State = 'Responding'
        $checks
    }
    function Restart-DockerContainerAndWait { throw 'Interrupted working LAN stream' }
    Assert-True (-not (Repair-PlexHostPort -RestartOnFailure)) 'Loopback issue falsely reported fixed'
}
Run-Test 'Plex host repair requires repeated failure of both endpoints' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Test-ContainerUrl { $true }
    function Test-HostUrl { $false }
    function Get-DockerServiceAvailability { $script:calls++; Availability | Where-Object Name -eq plex }
    function Start-Sleep {}
    function Restart-DockerContainerAndWait { $script:events += 'plex-restart'; $false }
    Assert-True (-not (Repair-PlexHostPort -RestartOnFailure)) 'Failed restart falsely reported fixed'
    Assert-True ($script:calls -eq 3 -and ($script:events -join ',') -eq 'plex-restart') 'Restart lacked persistent independent evidence'
}
Run-Test 'maintenance covers the task execution limit in both Kuma and Grafana' {
    Set-Item Function:Start-UptimeKumaMaintenance $realMaintenanceStart
    $DockerKumaMaintenanceIdPath = Join-Path $scratch 'kuma-maintenance.id'
    function Start-GrafanaMaintenance { param($TtlMinutes) Assert-True ($TtlMinutes -ge 150) 'Grafana expires before task deadline'; $true }
    function Invoke-WslCommand {
        param($Command)
        Assert-True ($Command -match '--ttl-minutes 150') 'Kuma expires before task deadline'
        [pscustomobject]@{ExitCode=0;Output='123'}
    }
    Assert-True (Start-UptimeKumaMaintenance) 'Maintenance could not start'
}
Run-Test 'healthy inventory preserves non-restarting stacks during daemon failure' {
    Set-Item Function:Save-DockerHealthyInventory $realHealthyInventorySave
    function Get-RunningWslComposeServiceNames { @('plex','ark-ascended') }
    Save-DockerHealthyInventory
    function Get-RunningWslComposeServiceNames { throw 'daemon unavailable' }
    function Restart-DockerDesktopClean { $true }
    function Start-CriticalDockerServices { $true }
    function Repair-WslComposeBindServices {
        param($ServiceNames)
        Assert-True ($ServiceNames -contains 'ark-ascended') 'Lost non-restarting stack'
        $true
    }
    function Repair-WindowsComposeServices { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop) 'Recovery using healthy inventory failed'
}
Run-Test 'missing or corrupt fallback inventory withholds broad recovery' {
    function Write-Log { param($Message) Add-Content -LiteralPath $logFilePath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message" }
    function Get-RunningWslComposeServiceNames { throw 'daemon unavailable' }
    function Restart-DockerDesktopClean { throw 'Restarted without inventory' }
    Assert-True (-not (Restart-DockerDesktop)) 'Missing inventory accepted'
    Set-Content -LiteralPath $DockerHealthyInventoryPath -Value '{}'
    Assert-True (-not (Restart-DockerDesktop)) 'Invalid inventory accepted'
    @{Services=@('plex');CapturedAt=[DateTimeOffset]::UtcNow.AddHours(-1).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $DockerHealthyInventoryPath
    Assert-True (-not (Restart-DockerDesktop)) 'Stale snapshot restarted possibly intentionally stopped services'
    Assert-True ($script:events.Count -eq 0) 'Withheld recovery changed maintenance'
    Assert-True (Test-DockerRestartAllowed) 'Preflight failures consumed restart cooldown or hourly limit'
}

Run-Test 'restart cooldown begins only after the final availability veto' {
    function Write-DockerLog { param($Message) Add-Content -LiteralPath $logFilePath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message" }
    function Test-DockerServiceOutage { $false }
    function Invoke-DockerCliWithTimeout { throw 'Restarted a responding service' }
    Assert-True (-not (Restart-DockerDesktopClean)) 'Service veto ignored'
    Assert-True (Test-DockerRestartAllowed) 'Service veto consumed cooldown'
    function Test-DockerServiceOutage { $true }
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=0;Output=''} }
    function Wait-DockerDesktopReady { $true }
    Assert-True (Restart-DockerDesktopClean) 'Admitted restart failed'
    Assert-True (-not (Test-DockerRestartAllowed)) 'Actual restart did not consume cooldown'
}

Run-Test 'resumed recovery recreates coverage when either maintenance channel is missing or empty' {
    function Start-CriticalDockerServices { $true }
    function Get-DockerPendingRecoveryTargets { [pscustomobject]@{Valid=$true;Services=@()} }
    function Repair-WslComposeBindServices { $true }
    function Test-DockerContainerReady { $true }
    function Get-ConfirmedDockerHealth { Health }
    foreach ($present in @($DockerKumaMaintenanceIdPath,$DockerGrafanaMaintenanceIdPath)) {
        foreach ($emptyPeer in @($false,$true)) {
            Remove-Item -LiteralPath $DockerKumaMaintenanceIdPath,$DockerGrafanaMaintenanceIdPath -ErrorAction SilentlyContinue
            Save-DockerRecoveryInventory -ServiceNames @('plex')
            Set-Content -LiteralPath $present -Value 'saved-window'
            if ($emptyPeer) {
                $peer = if ($present -eq $DockerKumaMaintenanceIdPath) { $DockerGrafanaMaintenanceIdPath } else { $DockerKumaMaintenanceIdPath }
                Set-Content -LiteralPath $peer -Value ''
            }
            $script:events = @()
            Assert-True (Restart-DockerDesktop -ResumeOnly) 'Resume failed'
            Assert-True (($script:events -join ',') -eq 'maintenance-start,maintenance-stop') 'Partial maintenance coverage was reused'
        }
    }
}

Run-Test 'responding services veto a second WSL shutdown after the first times out' {
    function Test-DockerServiceOutage { $script:calls++; $script:calls -eq 1 }
    function Invoke-ProcessWithTimeout { param($Arguments) $script:events += ($Arguments -join ' '); [pscustomobject]@{ExitCode=124;Output='timeout'} }
    function Request-DockerHostRecoveryReboot { throw 'Rebooted after services recovered' }
    Assert-True (-not (Stop-DockerWslForRecovery)) 'Reported successful recovery'
    Assert-True (($script:events -join ',') -eq '--shutdown') 'Repeated shutdown despite responding services'
}
Run-Test 'healthy snapshots update atomically and retain the previous inventory on query failure' {
    Set-Item Function:Save-DockerHealthyInventory $realHealthyInventorySave
    function Get-RunningWslComposeServiceNames { @('plex','ark-ascended') }
    Save-DockerHealthyInventory
    function Get-RunningWslComposeServiceNames { @('plex') }
    Save-DockerHealthyInventory
    function Get-RunningWslComposeServiceNames { throw 'query failed' }
    try { Save-DockerHealthyInventory } catch { }
    Assert-True ((@(Get-DockerRecoveryInventory -Path $DockerHealthyInventoryPath) -join ',') -eq 'plex') 'Failed query corrupted last snapshot'
}
Run-Test 'saved missing project is restored but failed inspection is deferred' {
    Set-Item Function:Get-DockerPendingRecoveryTargets $realPendingTargets
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$true;ExitCode=0;FailedServices=@()} }
    function Get-WslComposeContainers { @() }
    $targets = Get-DockerPendingRecoveryTargets -ServiceNames @('plex')
    Assert-True ($targets.Valid -and ($targets.Services -join ',') -eq 'plex') 'Missing project not restored'
    function Get-WslComposeContainers { throw 'Docker query failed' }
    Assert-True (-not (Get-DockerPendingRecoveryTargets -ServiceNames @('plex')).Valid) 'Query error treated as absence'
}
Run-Test 'critical startup clamps nested process timeouts and releases its budget afterward' {
    function Start-CriticalDockerServicesCore {
        $result = Invoke-ProcessWithTimeout -FilePath powershell.exe -Arguments @('-NoProfile','-Command','Start-Sleep -Seconds 10') -TimeoutSeconds 30 -Quiet
        Assert-True ($result.ExitCode -eq 124) 'Nested process ignored the shared budget'
        $false
    }
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    Assert-True (-not (Start-CriticalDockerServices -TimeoutSeconds 3)) 'Timed out startup reported success'
    Assert-True ($elapsed.Elapsed.TotalSeconds -lt 8) 'Critical startup exceeded budget plus process cleanup'
    Assert-True ((Get-DockerTimeoutSeconds -Requested 120) -eq 120) 'Budget leaked into later operations'
}
Run-Test 'bind repair clamps Compose and follow-up to its remaining phase budget' {
    New-Item -ItemType Directory -Path (Join-Path $DockerProjectRoot 'sunday-edge') -Force | Out-Null
    Set-Content (Join-Path $DockerProjectRoot 'sunday-edge/docker-compose.yml') 'services: {}'
    function Invoke-WslDockerCompose {
        param($TimeoutSeconds)
        Assert-True ($TimeoutSeconds -le 4) 'Compose received a fresh 300-second allowance'
        $script:calls++
        Start-Sleep -Milliseconds 1100
        [pscustomobject]@{ExitCode=0;Output=''}
    }
    function Invoke-WslCommand {
        param($TimeoutSeconds)
        Assert-True ($TimeoutSeconds -le 3) 'Follow-up reset the bind-repair deadline'
        $script:calls++
        [pscustomobject]@{ExitCode=0;Output=''}
    }
    Assert-True (Repair-WslComposeBindServices -ServiceNames @('sunday-edge') -TimeoutSeconds 5 -OnlySpecified) 'Bounded repair failed'
    Assert-True ($script:calls -eq 2) 'Did not exercise Compose and follow-up'
    Assert-True ((Get-DockerTimeoutSeconds -Requested 300) -eq 300) 'Bind budget leaked outside its phase'
}
Run-Test 'interrupted bind repair retains unfinished running projects and skips completed ones' {
    Set-Item Function:Get-DockerPendingRecoveryTargets $realPendingTargets
    Save-DockerRecoveryInventory -ServiceNames @('plex','homepage','mod-mc')
    function Test-DockerServiceOutage { $false }
    Assert-True (-not (Restart-DockerDesktopClean)) 'Veto ignored'
    Assert-True (@(Get-DockerRecoveryInventory -PendingBindRepair).Count -eq 0) 'Veto armed bind recreation'
    function Test-DockerServiceOutage { $true }
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=0;Output=''} }
    function Wait-DockerDesktopReady { $true }
    Assert-True (Restart-DockerDesktopClean) 'Admitted restart failed'
    function Invoke-WslDockerCompose {
        param($ProjectPath)
        $script:events += $ProjectPath
        [pscustomobject]@{ExitCode=$(if ($ProjectPath.EndsWith('/plex')) {0} else {1});Output=''}
    }
    Assert-True (-not (Repair-WslComposeBindServices -ServiceNames @('plex','homepage','mod-mc') -OnlySpecified)) 'Failed project reported repaired'
    Assert-True ((@(Get-DockerRecoveryInventory -PendingBindRepair) -join ',') -eq 'homepage,mod-mc') 'Unattempted project was lost or successful project retained'
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$true;ExitCode=0;FailedServices=@()} }
    function Get-WslComposeContainers { foreach ($name in @('plex','homepage','mod-mc')) { [pscustomobject]@{Project=$name;Status='running'} } }
    $targets = Get-DockerPendingRecoveryTargets -ServiceNames @(Get-DockerRecoveryInventory)
    Assert-True ($targets.Valid -and ($targets.Services -join ',') -eq 'homepage,mod-mc') 'Resume skipped unfinished running projects or repeated completed repair'
    function Invoke-WslDockerCompose { [pscustomobject]@{ExitCode=0;Output=''} }
    Assert-True (Repair-WslComposeBindServices -ServiceNames $targets.Services -OnlySpecified) 'Resume failed'
    Assert-True (@(Get-DockerRecoveryInventory -PendingBindRepair).Count -eq 0) 'Successful repairs stayed pending'
}
Run-Test 'critical startup clamps readiness waits to the same budget' {
    function Test-DockerContainerReady { $false }
    function Start-CriticalDockerServicesCore { Wait-DockerContainerReady -Name plex -TimeoutSeconds 180 -IntervalSeconds 1 }
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    Assert-True (-not (Start-CriticalDockerServices -TimeoutSeconds 3)) 'Timed out wait reported success'
    Assert-True ($elapsed.Elapsed.TotalSeconds -lt 5) 'Readiness reset the critical-startup budget'
}
Run-Test 'interrupted journal writes retain the previous complete state' {
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    function Set-Content { param($LiteralPath, $ErrorAction) [IO.File]::WriteAllText($LiteralPath, '{partial'); throw 'simulated interrupted writer' }
    $failed = $false
    try { Write-DockerStateJson -Path $DockerRecoveryInventoryPath -Value @{Services=@('sonarr')} } catch { $failed = $true }
    Assert-True ($failed -and (@(Get-DockerRecoveryInventory) -join ',') -eq 'plex') 'Partial write damaged durable recovery state'
    Remove-Item -LiteralPath $DockerRecoveryInventoryPath
    try { Save-DockerRecoveryInventory -ServiceNames @('sonarr') } catch { }
    Assert-True (-not (Test-Path -LiteralPath $DockerRecoveryInventoryPath)) 'Failed first write left a corrupt journal'
}
Run-Test 'definite reboot rejection does not consume cooldown while ambiguous timeout does' {
    $script:DockerOperationLock = [pscustomobject]@{}
    function Test-CurrentProcessElevated { $true }
    $script:rebootCode = 5
    function Invoke-ProcessWithTimeout { $script:calls++; [pscustomobject]@{ExitCode=$script:rebootCode;ExitConfirmed=($script:rebootCode -ne 124);Output='command result'} }
    try {
        Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Rejected reboot reported accepted'
        Assert-True (-not $script:DockerHostRebootRequested) 'Definite rejection retained reboot maintenance'
        $script:rebootCode = 124
        Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Timed out reboot reported accepted'
        Assert-True ($script:DockerHostRebootRequested) 'Ambiguous reboot would close maintenance too early'
        Assert-True ($script:calls -eq 2) 'Rejection incorrectly consumed cooldown'
        Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Ambiguous reboot allowed another attempt'
        Assert-True ($script:calls -eq 2) 'Ambiguous timeout did not retain cooldown'
    } finally { $script:DockerOperationLock = $null }
}
Run-Test 'broken optional notifications do not disable the health monitor' {
    $path = Join-Path $scratch 'broken-notifications.json'
    Set-Content -LiteralPath $path -Value '{truncated'
    Assert-True ((Get-DockerNotificationWebhook -Path $path) -ceq '') 'Malformed notifications did not fail open'
    function Get-Content { throw 'temporarily unreadable' }
    Assert-True ((Get-DockerNotificationWebhook -Path $path) -ceq '') 'Unreadable notifications did not fail open'
    function Get-ConfirmedDockerHealth { Health }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 0) 'Notification error stopped health monitoring'
}
Run-Test 'scheduled reboot retains maintenance and resumed recovery refreshes coverage before cleanup' {
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    function Start-UptimeKumaMaintenance {
        param($State)
        $State.Kuma=$true; $State.Grafana=$true
        $script:events += 'maintenance-start'
        Set-Content -LiteralPath $DockerKumaMaintenanceIdPath -Value '123'
        Set-Content -LiteralPath $DockerGrafanaMaintenanceIdPath -Value 'test-window'
        $true
    }
    function Stop-UptimeKumaMaintenance {
        $script:events += 'maintenance-stop'
        Remove-Item -LiteralPath $DockerKumaMaintenanceIdPath,$DockerGrafanaMaintenanceIdPath
        $true
    }
    function Restart-DockerDesktopClean { $script:DockerHostRebootRequested = $true; $false }
    Assert-True (-not (Restart-DockerDesktop)) 'Reboot reported immediate recovery'
    Assert-True (($script:events -join ',') -eq 'maintenance-start') 'Maintenance ended before reboot'
    Assert-True (Test-Path -LiteralPath $DockerKumaMaintenanceIdPath) 'Lost saved maintenance IDs'
    $script:DockerHostRebootRequested = $false
    function Restart-DockerDesktopClean { throw 'Resuming must not restart Desktop' }
    function Start-CriticalDockerServices { $true }
    function Get-DockerPendingRecoveryTargets { [pscustomobject]@{Valid=$true;Services=@()} }
    function Repair-WslComposeBindServices { $true }
    function Test-DockerContainerReady { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop -ResumeOnly) 'Resumed recovery failed'
    Assert-True (($script:events -join ',') -eq 'maintenance-start,maintenance-start,maintenance-stop') 'Resume did not refresh maintenance before cleanup'
    Assert-True (-not (Test-Path -LiteralPath $DockerGrafanaMaintenanceIdPath)) 'Grafana window not closed after resume'
}
Run-Test 'resuming after saved maintenance expires opens a fresh window' {
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    Set-Content -LiteralPath $DockerKumaMaintenanceIdPath -Value '123'
    [IO.File]::SetLastWriteTimeUtc($DockerKumaMaintenanceIdPath, [DateTime]::UtcNow.AddHours(-3))
    function Start-CriticalDockerServices { $true }
    function Get-DockerPendingRecoveryTargets { [pscustomobject]@{Valid=$true;Services=@()} }
    function Repair-WslComposeBindServices { $true }
    function Test-DockerContainerReady { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop -ResumeOnly) 'Resume after expiry failed'
    Assert-True (($script:events -join ',') -eq 'maintenance-start,maintenance-stop') 'Expired IDs prevented fresh maintenance'
}
Run-Test 'SWAG dependency failure cannot restart a responding proxy' {
    Set-Item Function:Test-DockerServiceOutage $realOutage
    function Test-DockerDaemon { $true }
    function Test-RequiredDockerNetwork { $true }
    function Start-DockerContainerIfPresent { $true }
    function Wait-DockerContainerReady { $true }
    function Wait-ContainerUrl { $true }
    function Repair-PlexHostPort { $true }
    function Test-SwagDependencyEndpoints { $false }
    $script:proxyResponding = $true
    function Get-DockerServiceAvailability {
        param($ServiceNames)
        Assert-True (($ServiceNames -join ',') -eq 'swag-http,swag-https') 'SWAG must check its own exposed ports'
        $script:calls++
        foreach ($address in @('127.0.0.1','192.168.50.40')) {
            foreach ($name in $ServiceNames) {
                [pscustomobject]@{Name=$name;Address=$address;State=$(if ($script:proxyResponding) {'Responding'} else {'Unavailable'})}
            }
        }
    }
    function Start-Sleep {}
    function Restart-DockerContainerAndWait { $script:events += 'swag-restart'; $false }
    Assert-True (-not (Start-CriticalDockerServices)) 'Dependency failure falsely reported fixed'
    Assert-True ($script:events.Count -eq 0) 'Restarted a working proxy'
    $script:proxyResponding = $false
    Assert-True (-not (Start-CriticalDockerServices)) 'Failed proxy restart reported fixed'
    Assert-True ($script:calls -eq 4 -and ($script:events -join ',') -eq 'swag-restart') 'Proxy restart lacked repeated independent failures'
}
Run-Test 'fresh ID timestamps never suppress overlap and all old and new windows are closed' {
    Set-Item Function:Start-UptimeKumaMaintenance $realMaintenanceStart
    Set-Item Function:Stop-UptimeKumaMaintenance $realMaintenanceStop
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    $oldGrafana = '11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222'
    $newGrafana = '33333333-3333-3333-3333-333333333333:44444444-4444-4444-4444-444444444444'
    Add-DockerMaintenanceToken -Path $DockerKumaMaintenanceIdPath -Token '123'
    Add-DockerMaintenanceToken -Path $DockerGrafanaMaintenanceIdPath -Token $oldGrafana
    function Invoke-WslCommand {
        param($Command)
        $script:events += $Command
        $output = if ($Command -match 'grafana-maintenance.py start') { $newGrafana } elseif ($Command -match 'kuma-maintenance.py start') { '456' } else { '' }
        [pscustomobject]@{ExitCode=0;Output=$output}
    }
    function Start-CriticalDockerServices { $true }
    function Get-DockerPendingRecoveryTargets { [pscustomobject]@{Valid=$true;Services=@()} }
    function Repair-WslComposeBindServices { $true }
    function Test-DockerContainerReady { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop -ResumeOnly) 'Near-expiry resume failed'
    Assert-True ($script:events.Count -eq 6 -and $script:events[0] -match 'grafana-maintenance.py start' -and $script:events[1] -match 'kuma-maintenance.py start') 'Old maintenance closed before new windows existed'
    foreach ($id in @('123','456',$oldGrafana,$newGrafana)) {
        Assert-True (@($script:events | Where-Object { $_.EndsWith('stop ' + $id) }).Count -eq 1) 'An overlapping window was orphaned'
    }
    Assert-True (-not (Test-Path -LiteralPath $DockerKumaMaintenanceIdPath)) 'Kuma IDs remained after cleanup'
    Assert-True (-not (Test-Path -LiteralPath $DockerGrafanaMaintenanceIdPath)) 'Grafana IDs remained after cleanup'
}
Run-Test 'failed maintenance cleanup retains only the failed IDs for retry' {
    Set-Item Function:Stop-UptimeKumaMaintenance $realMaintenanceStop
    Add-DockerMaintenanceToken -Path $DockerKumaMaintenanceIdPath -Token '123'
    Add-DockerMaintenanceToken -Path $DockerKumaMaintenanceIdPath -Token '456'
    function Invoke-WslCommand { param($Command) Assert-True ($Command -match 'kuma-maintenance.py --strict stop') 'Kuma failure would be reported as success'; [pscustomobject]@{ExitCode=$(if ($Command.EndsWith('stop 123')) {1} else {0});Output=''} }
    Assert-True (-not (Stop-UptimeKumaMaintenance)) 'Failed cleanup reported success'
    Assert-True ((Get-Content -LiteralPath $DockerKumaMaintenanceIdPath) -eq '123') 'Failed cleanup lost its retry ID'
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output=''} }
    Assert-True (Stop-UptimeKumaMaintenance) 'Cleanup retry failed'
    Assert-True (-not (Test-Path -LiteralPath $DockerKumaMaintenanceIdPath)) 'Successful retry left stale IDs'
}

foreach ($failedChannel in @('Kuma','Grafana')) {
    Run-Test "partial $failedChannel maintenance is retried after readiness without duplicating the successful channel" {
        Set-Item Function:Start-UptimeKumaMaintenance $realMaintenanceStart
        Set-Item Function:Stop-UptimeKumaMaintenance $realMaintenanceStop
        Save-DockerRecoveryInventory -ServiceNames @('plex')
        $script:maintenancePhase = 'before'
        function Invoke-WslCommand {
            param($Command)
            $script:events += $Command
            $isGrafana = $Command -match 'grafana-maintenance.py'
            $isStart = $Command -match '.py start '
            $channel = if ($isGrafana) { 'Grafana' } else { 'Kuma' }
            if ($isStart -and $channel -eq $failedChannel -and $script:maintenancePhase -eq 'before') {
                return [pscustomobject]@{ExitCode=1;Output='unavailable'}
            }
            $token = if ($isGrafana) { '11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222' } else { '123' }
            [pscustomobject]@{ExitCode=0;Output=$(if ($isStart) {$token} else {''})}
        }
        function Restart-DockerDesktopClean { $true }
        function Start-CriticalDockerServices { $script:maintenancePhase='ready'; $true }
        function Repair-WslComposeBindServices {
            Assert-True ($maintenanceState.Kuma -and $maintenanceState.Grafana) 'Bind repair skipped missing maintenance channel retry'
            $true
        }
        function Repair-WindowsComposeServices { $true }
        function Get-ConfirmedDockerHealth { Health }
        Assert-True (Restart-DockerDesktop) 'Recovery failed after maintenance retry'
        foreach ($channel in @('Kuma','Grafana')) {
            $expected = if ($channel -eq $failedChannel) {2} else {1}
            $pattern = $channel.ToLower() + '-maintenance.py start'
            Assert-True (@($script:events | Where-Object { $_ -match $pattern }).Count -eq $expected) 'Missing channel not retried or successful channel duplicated'
        }
        Assert-True (-not (Test-Path $DockerKumaMaintenanceIdPath) -and -not (Test-Path $DockerGrafanaMaintenanceIdPath)) 'Partial maintenance cleanup was lost'
    }
}

Run-Test 'Discord transport failures have a bounded request and do not escape into recovery' {
    Set-Item Function:Send-DiscordAlert $realDiscordAlert
    $discordWebhookUrl = 'https://notification.invalid/test-secret'
    function Invoke-RestMethod {
        param($TimeoutSec,[switch]$UseBasicParsing)
        Assert-True ($TimeoutSec -gt 0 -and $TimeoutSec -le 15 -and $UseBasicParsing) 'Notification request is unbounded'
        $script:calls++
        throw 'notification timed out at https://notification.invalid/test-secret'
    }
    function Write-Log { param($Message) Assert-True ($Message -notmatch 'test-secret') 'Notification credential leaked' }
    Send-DiscordAlert -title 'test' -description 'test'
    Assert-True ($script:calls -eq 1) 'Notification failure prevented return to recovery'
}

Run-Test 'failed Docker process termination aborts hard recovery before WSL shutdown or relaunch' {
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=1;Output='failed'} }
    function Stop-DockerDesktopProcessTree { $false }
    function Stop-DockerWslForRecovery { throw 'Shut down WSL with surviving Docker processes' }
    function Start-DockerDesktopServiceIfAvailable { throw 'Launched against surviving Docker processes' }
    Assert-True (-not (Invoke-DockerDesktopHardRecovery -ShutdownWsl)) 'Failed termination was ignored'
}

Run-Test 'accepted termination cannot hide surviving Docker processes' {
    function Get-Process { [pscustomobject]@{Id=424242;ProcessName='mock-docker';StartTime=(Get-Date)} }
    function Stop-Process { }
    function Start-DockerRetrySleep { }
    Assert-True (-not (Stop-DockerDesktopProcessTree)) 'Accepted termination was mistaken for actual process exit'
    $script:calls = 0
    function Get-Process { $script:calls++; if ($script:calls -eq 1) { [pscustomobject]@{Id=424242;ProcessName='mock-docker';StartTime=(Get-Date)} } }
    Assert-True (Stop-DockerDesktopProcessTree) 'Confirmed process exit was rejected'
}

Run-Test 'targeted repair retries a missing maintenance channel and retains cleanup for partial success' {
    function Get-ConfirmedDockerHealth { Health 'Sentinel' $true @('homepage') }
    function Start-UptimeKumaMaintenance {
        param($State)
        $script:calls++
        $State.Grafana=$true
        if ($script:calls -eq 2) { $State.Kuma=$true }
        $true
    }
    function Repair-ConfirmedDockerServiceHealth {
        Assert-True ($maintenanceState.Kuma -and $maintenanceState.Grafana) 'Missing maintenance channel not retried before targeted mutation'
        $true
    }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Persistent sentinel falsely reported recovered'
    Assert-True ($script:calls -eq 2 -and ($script:events -join ',') -eq 'maintenance-stop') 'Missing channel retry or partial cleanup was lost'
}

Run-Test 'final health cannot be Healthy while the independent Windows Plex endpoint fails' {
    function Test-DockerDaemon { $true }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output=''} }
    function Test-RequiredDockerNetwork { $true }
    function Test-DockerContainerReady { $true }
    function Test-ContainerUrl { $true }
    function Test-HostUrl { param($Url) Assert-True ($Url -eq 'http://127.0.0.1:32400/identity') 'Wrong host endpoint'; $false }
    Assert-True ((Get-DockerHealthSnapshot).Kind -eq 'CriticalService') 'Failed Windows forwarding reported Healthy'
}

Run-Test 'backend recovery during setup vetoes CLI restart and hard escalation despite unavailable applications' {
    Set-Item Function:Test-DockerBackendRecoveryRequired $realBackendRequired
    function Get-DockerHealthSnapshot { Health 'CriticalService' }
    function Invoke-DockerCliWithTimeout { throw 'Mutated a recovered engine' }
    function Stop-DockerDesktopProcessTree { throw 'Stopped a recovered engine' }
    Assert-True (-not (Restart-DockerDesktopClean -ExpectedKind WslTransport)) 'Recovered backend still restarted'
    Assert-True (-not (Invoke-DockerDesktopHardRecovery)) 'Recovered backend still escalated'
    function Get-DockerHealthSnapshot { Health 'Daemon' }
    Assert-True (-not (Restart-DockerDesktopClean -ExpectedKind WslTransport)) 'Changed backend failure matched stale admission'
}

Run-Test 'maintenance ID write failures clean up returned windows and do not abort recovery' {
    Set-Item Function:Start-UptimeKumaMaintenance $realMaintenanceStart
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    function Add-DockerMaintenanceToken { throw 'ID file temporarily unwritable' }
    function Invoke-WslCommand {
        param($Command)
        $script:events += $Command
        $token = if ($Command -match 'grafana-maintenance.py') { '11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222' } else { '123' }
        [pscustomobject]@{ExitCode=0;Output=$(if ($Command -match '.py start ') {$token} else {''})}
    }
    function Restart-DockerDesktopClean { $true }
    function Start-CriticalDockerServices { $true }
    function Repair-WslComposeBindServices { $script:calls++; $true }
    function Repair-WindowsComposeServices { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop) 'Optional maintenance storage failure aborted recovery'
    Assert-True ($script:calls -eq 1) 'Repair did not continue after maintenance failure'
    Assert-True (@($script:events | Where-Object { $_ -match ' stop ' }).Count -eq 4) 'Created remote windows were not cleaned up when their IDs could not be saved'
}

Run-Test 'unexpected maintenance setup exceptions preserve existing partial cleanup state' {
    Set-Item Function:Start-UptimeKumaMaintenance $realMaintenanceStart
    function Write-DockerLog { throw 'logger unavailable' }
    $state = @{Grafana=$true}
    Assert-True (Start-UptimeKumaMaintenance -State $state) 'Setup exception discarded existing Grafana cleanup'
    Assert-True (-not $state.Kuma) 'Failed Kuma setup was marked ready'
}

Run-Test 'critical repair retries Kuma maintenance after readiness and before Plex startup' {
    $state = @{Grafana=$true}
    $script:kumaReady = $false
    function Test-DockerDaemon { $true }
    function Test-RequiredDockerNetwork { $true }
    function Start-DockerContainerIfPresent { param($Name) $script:events += $Name; $true }
    function Wait-DockerContainerReady { $true }
    function Wait-ContainerUrl { param($ContainerName) if ($ContainerName -eq 'uptime-kuma') { $script:kumaReady=$true }; $true }
    function Start-UptimeKumaMaintenance {
        param($State)
        Assert-True ($script:kumaReady) 'Retried before Kuma became reachable'
        $script:events += 'maintenance'
        $State.Kuma=$true
        $true
    }
    function Repair-PlexHostPort { $true }
    function Test-SwagDependencyEndpoints { $true }
    function Wait-TcpPort { $true }
    Assert-True (Repair-ConfirmedDockerServiceHealth -Health (Health 'CriticalService') -MaintenanceState $state) 'Critical repair failed'
    Assert-True (($script:events -join ',') -eq 'socket-proxy,uptime-kuma,maintenance,plex,swag') 'Maintenance did not precede later service mutations'
    Assert-True ($state.Kuma) 'Caller lost maintenance cleanup state'
}

Run-Test 'maintenance first established during critical startup is closed by the recovery caller' {
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    function Start-UptimeKumaMaintenance { $false }
    function Restart-DockerDesktopClean { $true }
    function Start-CriticalDockerServices { param($MaintenanceState) $MaintenanceState.Kuma=$true; $MaintenanceState.Grafana=$true; $true }
    function Repair-WslComposeBindServices { $true }
    function Repair-WindowsComposeServices { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop) 'Recovery failed'
    Assert-True (($script:events -join ',') -eq 'maintenance-stop') 'Maintenance established during startup was orphaned'
}
