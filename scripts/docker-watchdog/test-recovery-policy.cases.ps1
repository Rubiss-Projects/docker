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
Run-Test 'pending journal only selects stopped containers and confirmed bad mounts' {
    Set-Item Function:Get-DockerPendingRecoveryTargets $realPendingTargets
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$false;ExitCode=1;FailedServices=@('homepage')} }
    function Get-DockerContainerState {
        param($Name)
        [pscustomobject]@{Status=$(if ($Name -eq 'sonarr') {'exited'} else {'running'});Health='unhealthy'}
    }
    $targets = Get-DockerPendingRecoveryTargets -ServiceNames @('channels-dvr','sonarr','transmission')
    Assert-True ($targets.Valid -and ($targets.Services -join ',') -eq 'homepage,sonarr') 'Recreated working or RPC-busy containers'
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$false;ExitCode=124;FailedServices=@()} }
    Assert-True (-not (Get-DockerPendingRecoveryTargets -ServiceNames @('channels-dvr')).Valid) 'Probe timeout authorized bind repair'
}
