# Runs only after Docker recovery completes, under the existing Windows lock.
function Invoke-CaddyPlexHealth {
    param([switch]$Repair)
    $arguments = @('-d', 'Ubuntu', '-u', 'root', '--', 'python3', '/usr/local/lib/caddy-plex/health.py')
    if ($Repair) { $arguments += '--repair' }
    $result = Invoke-ProcessWithTimeout -FilePath 'wsl.exe' -Arguments $arguments -TimeoutSeconds 45 -Quiet
    Write-DockerLog "Caddy-only health/remediation exit=$($result.ExitCode): $($result.Output)"
    # This return value never enters Docker's daemon/service failure classifier.
    return ($result.ExitCode -eq 0)
}
