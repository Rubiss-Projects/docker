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
    param ([string[]]$ServiceNames = @('channels-dvr', 'plex', 'sonarr', 'radarr'))
    foreach ($address in $DockerAvailabilityHosts) {
        foreach ($service in ($DockerAvailabilityServices | Where-Object { $ServiceNames -contains $_.Name })) {
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
    param (
        [ValidateRange(1, 3)][int]$Attempts = 3,
        [int]$RetryDelaySeconds = 30,
        [ValidateSet('channels-dvr', 'plex', 'sonarr', 'radarr')]
        [string[]]$ServiceNames = @('channels-dvr', 'plex', 'sonarr', 'radarr')
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $checks = @(Get-DockerServiceAvailability -ServiceNames $ServiceNames)
        $expectedCount = $DockerAvailabilityHosts.Count * @($ServiceNames | Sort-Object -Unique).Count
        if ($expectedCount -lt 2 -or $checks.Count -ne $expectedCount) {
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
    try { $containers = @(Get-WslComposeContainers -All) }
    catch {
        Write-DockerLog 'Pending recovery deferred: cannot inspect Compose projects.'
        return [pscustomobject]@{ Valid = $false; Services = @() }
    }
    foreach ($name in $ServiceNames) {
        # Query failures must not be interpreted as permission to recreate a stack.
        $members = @($containers | Where-Object Project -eq $name)
        if ($members.Count -eq 0) {
            Write-DockerLog "Pending recovery deferred: cannot inspect $name."
            return [pscustomobject]@{ Valid = $false; Services = @() }
        }
        if (@($members | Where-Object Status -eq 'running').Count -eq 0) { $targets += $name }
        # Running projects need an explicit sentinel failure. An RPC timeout or
        # a completed one-shot auxiliary container does not authorize recreation.
    }
    return [pscustomobject]@{ Valid = $true; Services = @($targets | Sort-Object -Unique) }
}
