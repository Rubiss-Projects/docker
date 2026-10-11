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
    function Get-RunningWslComposeServiceNames { throw 'daemon unavailable' }
    function Restart-DockerDesktopClean { throw 'Restarted without inventory' }
    Assert-True (-not (Restart-DockerDesktop)) 'Missing inventory accepted'
    Set-Content -LiteralPath $DockerHealthyInventoryPath -Value '{}'
    Assert-True (-not (Restart-DockerDesktop)) 'Invalid inventory accepted'
    @{Services=@('plex');CapturedAt=[DateTimeOffset]::UtcNow.AddHours(-1).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $DockerHealthyInventoryPath
    Assert-True (-not (Restart-DockerDesktop)) 'Stale snapshot restarted possibly intentionally stopped services'
    Assert-True ($script:events.Count -eq 0) 'Withheld recovery changed maintenance'
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
        $script:rebootCode = 124
        Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Timed out reboot reported accepted'
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
