# Windows-native probes intentionally avoid Docker, WSL, DNS, and HTTP proxies.
# Any HTTP response vetoes a broad restart; it does not assert application health.
$DockerAvailabilityHosts = @('127.0.0.1', '192.168.50.40')
$DockerAvailabilityServices = @(
    @{ Name = 'channels-dvr'; Path = ':8089/' },
    @{ Name = 'plex'; Path = ':32400/identity' },
    @{ Name = 'sonarr'; Path = ':8989/ping' },
    @{ Name = 'radarr'; Path = ':7878/ping' }
)

function Get-DockerServiceAvailability {
    foreach ($address in $DockerAvailabilityHosts) {
        foreach ($service in $DockerAvailabilityServices) {
            $url = 'http://' + $address + $service.Path
            try {
                $result = Invoke-ProcessWithTimeout -FilePath "$env:SystemRoot\System32\curl.exe" -Arguments @(
                    '--noproxy', '*', '--connect-timeout', '2', '--max-time', '5',
                    '--silent', '--output', 'NUL', '--write-out', '%{http_code}', $url
                ) -TimeoutSeconds 8 -Quiet
                $status = $result.Output.Trim()
                $state = 'Unknown'
                if ($result.ExitCode -eq 0 -and $status -match '^[1-5][0-9]{2}$') {
                    $state = 'Responding'
                } elseif ($result.ExitCode -in @(7, 28, 52, 55, 56) -and $status -eq '000') {
                    $state = 'Unavailable'
                }
            } catch {
                # A missing/broken probe executable is not evidence of an outage.
                $state = 'Unknown'
            }
            [pscustomobject]@{ Name = $service.Name; Address = $address; State = $state }
        }
    }
}

function Test-DockerServiceOutage {
    param ([ValidateRange(1, 3)][int]$Attempts = 3, [int]$RetryDelaySeconds = 30)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $checks = @(Get-DockerServiceAvailability)
        $expectedCount = $DockerAvailabilityHosts.Count * $DockerAvailabilityServices.Count
        if ($expectedCount -lt 4 -or $checks.Count -ne $expectedCount) {
            Write-DockerLog 'Recovery withheld: incomplete independent service checks.'
            return $false
        }
        $summary = ($checks | ForEach-Object { "$($_.Name)@$($_.Address)=$($_.State)" }) -join ', '
        Write-DockerLog "Independent outage check $attempt/$Attempts`: $summary"
        if (@($checks | Where-Object { $_.State -ne 'Unavailable' }).Count -gt 0) {
            Write-DockerLog 'Recovery withheld: at least one service responds or a probe is inconclusive.'
            return $false
        }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds $RetryDelaySeconds }
    }
    return $true
}

function Test-DockerAutomaticRecoveryAllowed {
    try {
        $boot = (Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime
        if ($null -eq $boot -or (Get-Date) -lt $boot.AddMinutes(10)) {
            Write-DockerLog 'Recovery withheld: Windows startup has a ten-minute grace period.'
            return $false
        }
    } catch {
        Write-DockerLog 'Recovery withheld: unable to establish Windows startup grace period.'
        return $false
    }
    return Test-DockerServiceOutage
}

function Get-DockerPendingRecoveryTargets {
    param ([string[]]$ServiceNames)
    $sentinel = Get-StatefulServiceSentinelResult -MaxAttempts 1
    if (-not $sentinel.Healthy -and ($sentinel.ExitCode -ne 1 -or $sentinel.FailedServices.Count -eq 0)) {
        Write-DockerLog 'Pending recovery deferred: mount verification was inconclusive.'
        return [pscustomobject]@{ Valid = $false; Services = @() }
    }
    $targets = @($sentinel.FailedServices)
    foreach ($name in $ServiceNames) {
        # Query failures must not be interpreted as permission to recreate a stack.
        $state = Get-DockerContainerState -Name $name
        if ($null -eq $state) {
            Write-DockerLog "Pending recovery deferred: cannot inspect $name."
            return [pscustomobject]@{ Valid = $false; Services = @() }
        }
        if ($state.Status -ne 'running') { $targets += $name }
        # An RPC health timeout alone is insufficient evidence for recreation.
    }
    return [pscustomobject]@{ Valid = $true; Services = @($targets | Sort-Object -Unique) }
}
