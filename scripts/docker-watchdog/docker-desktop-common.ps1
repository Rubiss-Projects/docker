# Shared Docker Desktop maintenance helpers.
param ([string]$ProjectRoot = 'E:\Docker')
. (Join-Path $ProjectRoot 'scripts\grafana-maintenance.ps1')
. (Join-Path $PSScriptRoot 'recovery-policy.ps1')
# These functions are designed for Windows Task Scheduler scripts.

$DockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$DockerCliPath = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$DockerLogFilePath = "E:\Scripts\Logs\docker-desktop-logs.txt"
$DockerMaintenanceLockPath = "E:\Scripts\Logs\docker-maintenance.lock"
$DockerKumaMaintenanceIdPath = "E:\Scripts\Logs\docker-kuma-maintenance.id"
# Covers the scheduled task's two-hour execution limit plus cleanup/reboot grace.
# Successful recovery still closes maintenance immediately in its finally block.
$DockerKumaMaintenanceTtlMinutes = 150
$DockerOperationLockPath = "E:\Scripts\Logs\docker-health-monitor.lock"
$DockerRecoveryInventoryPath = "E:\Scripts\Logs\docker-recovery-services.json"
$DockerHealthyInventoryPath = "E:\Scripts\Logs\docker-last-healthy-services.json"
$DockerHostRebootPath = "E:\Scripts\Logs\docker-host-reboot.json"
$DockerProjectRoot = $ProjectRoot
$DockerDesktopProcessNames = @("Docker Desktop", "com.docker.backend", "com.docker.build", "docker-agent")
$DockerComposeProjects = @{
    "socket-proxy" = "/mnt/e/Docker/socket-proxy"
    "uptime-kuma" = "/mnt/e/Docker/uptime-kuma"
    "plex" = "/mnt/e/Docker/plex"
    "swag" = "/mnt/e/Docker/swag"
}
$DockerWindowsComposeProjects = @{
    "cadvisor" = "E:\Docker\cadvisor"
}

$DockerWslBindRepairOrder = @(
    "socket-proxy",
    "uptime-kuma",
    "plex",
    "swag",
    "tracearr",
    "bitwarden",
    "homepage",
    "prowlarr",
    "radarr",
    "sonarr",
    "bazarr",
    "transmission",
    "audiobookshelf",
    "bookshelf",
    "bookshelf-audio",
    "calibre",
    "recyclarr",
    "unpackerr",
    "speedtesttracker",
    "influxdb",
    "grafana",
    "portainer",
    "channels-dvr",
    "nvidia-smi-rest",
    "valheim"
)

function Write-DockerLog {
    param ([Parameter(Mandatory = $true)][string]$Message)

    $logDirectory = Split-Path -Path $DockerLogFilePath -Parent
    if (-not (Test-Path $logDirectory)) {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    }

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "$timestamp - $Message"
    Add-Content -Path $DockerLogFilePath -Value $logMessage
    Write-Host $logMessage
}

function Test-CurrentProcessElevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Enter-DockerOperationLock {
    param ([ValidateRange(0, 300)][int]$WaitSeconds = 0)

    # Recovery can wait for short controller runs; ordinary callers still try once.
    # Keep the OS handle for mutual exclusion. Never evict an owner by file age.
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        $stream = $null
        $opening = $true
        try {
            $directory = Split-Path $DockerOperationLockPath -Parent
            if (-not (Test-Path $directory)) { New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null }
            $stream = [System.IO.File]::Open($DockerOperationLockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::Read)
            $opening = $false
            $stream.SetLength(0)
            $bytes = [Text.Encoding]::UTF8.GetBytes("PID=$PID`r`nStarted=$(Get-Date -Format o)`r`n")
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush()
            $script:DockerOperationLock = $stream
            return $true
        } catch {
            if ($stream) { $stream.Dispose() }
            $failure = $_.Exception.GetBaseException()
            $nativeCode = $failure.HResult -band 0xffff
            if (-not ($opening -and $failure -is [IO.IOException] -and $nativeCode -in @(32, 33))) {
                Write-DockerLog "Docker operation lock failed ($($failure.GetType().Name), code $nativeCode): $($failure.Message)"
                return $false
            }
        }
        $remainingMs = ($WaitSeconds * 1000) - $timer.Elapsed.TotalMilliseconds
        if ($remainingMs -gt 0) {
            Start-Sleep -Milliseconds ([int][Math]::Min(250, [Math]::Ceiling($remainingMs)))
        }
    } while ($timer.Elapsed.TotalSeconds -lt $WaitSeconds)

    Write-DockerLog "Docker operation lock is busy after waiting up to $WaitSeconds seconds; leaving the active operation untouched."
    return $false
}

function Exit-DockerOperationLock {
    if ($script:DockerOperationLock) {
        $script:DockerOperationLock.Dispose()
        $script:DockerOperationLock = $null
    }
    # Leave the unlocked file in place to avoid a release/delete/acquire race.
}

function ConvertTo-WindowsProcessArgument {
    param ([AllowEmptyString()][string]$Argument)
    # Start-Process joins argv with spaces, so quote entries explicitly.
    # WSL parses leading option tokens itself and rejects quoted switches.
    if ($Argument.Length -gt 0 -and $Argument -notmatch '[\s"]') { return $Argument }
    $escaped = [regex]::Replace($Argument, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Get-DockerTimeoutSeconds {
    param ([int]$Requested)
    # PowerShell's caller scope carries the critical-startup budget through all
    # nested probes/Compose calls without resetting it for each operation.
    if ($null -ne $DockerCriticalTimer) {
        $remaining = [Math]::Floor($DockerCriticalBudgetSeconds - $DockerCriticalTimer.Elapsed.TotalSeconds)
        if ($remaining -lt 1) { throw [TimeoutException]::new('Critical startup deadline exceeded.') }
        return [int][Math]::Min($Requested, $remaining)
    }
    return $Requested
}

function Start-DockerRetrySleep {
    param ([int]$Seconds)
    Start-Sleep -Seconds (Get-DockerTimeoutSeconds -Requested $Seconds)
}

function Invoke-ProcessWithTimeout {
    param (
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 120,
        [switch]$Quiet
    )

    $TimeoutSeconds = Get-DockerTimeoutSeconds -Requested $TimeoutSeconds
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    $process = $null
    try {
        $startArgs = @{ FilePath = $FilePath; WindowStyle = 'Hidden'; PassThru = $true; RedirectStandardOutput = $stdoutPath; RedirectStandardError = $stderrPath; ErrorAction = 'Stop' }
        if ($Arguments.Count -gt 0) {
            $startArgs.ArgumentList = ($Arguments | ForEach-Object { ConvertTo-WindowsProcessArgument $_ }) -join ' '
        }
        $process = Start-Process @startArgs
        # Windows PowerShell 5.1 loses ExitCode without a retained handle.
        $processHandle = $process.Handle
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $process.Kill($true)
            } catch {
                & "$env:SystemRoot\System32\taskkill.exe" /F /T /PID $process.Id 2>&1 | Out-Null
                try { if (-not $process.HasExited) { $process.Kill() } } catch { }
            }
            $process.WaitForExit(5000) | Out-Null
            if (-not $Quiet) {
                Write-DockerLog "Process timed out after $TimeoutSeconds seconds: $FilePath $($Arguments -join ' ')"
            }
            return [pscustomobject]@{ ExitCode = 124; ExitConfirmed = $false; Output = "Timed out after $TimeoutSeconds seconds" }
        }

        $process.WaitForExit()
        $exitCode = $process.ExitCode
        if ($null -eq $exitCode) { throw 'Process exited, but its exit code could not be read.' }
        $stdout = Get-Content -Path $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -Path $stderrPath -Raw -ErrorAction SilentlyContinue
        $outputText = (@($stdout, $stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n"
        return [pscustomobject]@{ ExitCode = [int]$exitCode; ExitConfirmed = $true; Output = $outputText.Replace([string][char]0, '').Trim() }
    } catch {
        if (-not $Quiet) {
            Write-DockerLog "Process failed: $FilePath $($Arguments -join ' ') Error: $($_.Exception.Message)"
        }
        return [pscustomobject]@{ ExitCode = 1; ExitConfirmed = $false; Output = $_.Exception.Message }
    } finally {
        if ($process) { $process.Dispose() }
        Remove-Item -Path $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-DockerCli {
    param (
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Quiet,
        [int]$TimeoutSeconds = 30
    )

    if (-not (Test-Path $DockerCliPath)) {
        if (-not $Quiet) {
            Write-DockerLog "Docker CLI not found at $DockerCliPath"
        }
        return [pscustomobject]@{ ExitCode = 127; Output = "Docker CLI not found" }
    }

    return Invoke-DockerCliWithTimeout -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds -Quiet:$Quiet
}

function Invoke-DockerCliWithTimeout {
    param (
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [int]$TimeoutSeconds = 120,
        [switch]$Quiet
    )

    if (-not (Test-Path $DockerCliPath)) {
        if (-not $Quiet) {
            Write-DockerLog "Docker CLI not found at $DockerCliPath"
        }
        return [pscustomobject]@{ ExitCode = 127; Output = "Docker CLI not found" }
    }

    $result = Invoke-ProcessWithTimeout -FilePath $DockerCliPath -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds -Quiet:$Quiet
    if ($result.ExitCode -ne 0 -and -not $Quiet) {
        Write-DockerLog "docker $($Arguments -join ' ') failed with exit code $($result.ExitCode). Output: $($result.Output)"
    }

    return $result
}

function Stop-DockerDesktopProcessTree {
    $processes = Get-Process -Name $DockerDesktopProcessNames -ErrorAction SilentlyContinue
    if (-not $processes) {
        Write-DockerLog "No Docker Desktop processes are currently running."
        return $true
    }

    $allStopped = $true
    foreach ($process in $processes) {
        $startTimeText = "unknown"
        try { $startTimeText = $process.StartTime.ToString("yyyy-MM-dd HH:mm:ss") } catch { }
        Write-DockerLog "Stopping Docker process '$($process.ProcessName)' PID=$($process.Id) Started=$startTimeText."

        try {
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
        } catch {
            Write-DockerLog "Stop-Process failed for PID $($process.Id): $($_.Exception.Message)"
            $taskkill = Invoke-ProcessWithTimeout -FilePath "taskkill.exe" -Arguments @("/F", "/T", "/PID", $process.Id.ToString()) -TimeoutSeconds 20 -Quiet
            if ($taskkill.ExitCode -ne 0) {
                Write-DockerLog "taskkill failed for PID $($process.Id) with exit code $($taskkill.ExitCode). Output: $($taskkill.Output)"
                $allStopped = $false
            }
        }
    }

    Start-DockerRetrySleep -Seconds 5
    return $allStopped
}

function Start-DockerDesktopServiceIfAvailable {
    $service = Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue
    if (-not $service) {
        Write-DockerLog "Docker Desktop Windows service com.docker.service was not found."
        return $false
    }

    if ($service.Status -eq "Running") {
        Write-DockerLog "Docker Desktop Windows service com.docker.service is already running."
        return $true
    }

    try {
        Write-DockerLog "Starting Docker Desktop Windows service com.docker.service."
        Start-Service -Name "com.docker.service" -ErrorAction Stop
        return $true
    } catch {
        Write-DockerLog "Could not start com.docker.service. This usually means the task is not running elevated. Error: $($_.Exception.Message)"
        return $false
    }
}

function Save-DockerRecoveryInventory {
    param ([string[]]$ServiceNames)
    # Keep the original inventory across failed recovery attempts and host boots.
    if (-not (Test-Path -LiteralPath $DockerRecoveryInventoryPath)) {
        Write-DockerStateJson -Path $DockerRecoveryInventoryPath -Value @{
            Services = @($ServiceNames); CapturedAt = [DateTimeOffset]::UtcNow.ToString('o')
        }
    }
}

function Get-DockerRecoveryInventory {
    param ([string]$Path = $DockerRecoveryInventoryPath, [switch]$RequireRecent)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $state = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    if ($null -eq $state.Services) { throw 'The saved Docker recovery inventory is invalid.' }
    if ($RequireRecent) {
        $captured = [DateTimeOffset]::Parse($state.CapturedAt)
        $age = [DateTimeOffset]::UtcNow - $captured
        if ($age.TotalMinutes -gt 30 -or $age.TotalMinutes -lt -1) { throw 'The healthy inventory snapshot is stale or has an invalid timestamp.' }
    }
    foreach ($name in $state.Services) {
        if ($name -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$') { throw 'The saved Docker recovery inventory contains an invalid service.' }
        $name
    }
}

function Save-DockerHealthyInventory {
    # Refresh only during a fully healthy observation, never from a partially
    # restarted engine. Atomic replacement preserves the prior snapshot on error.
    $names = @(Get-RunningWslComposeServiceNames)
    Write-DockerStateJson -Path $DockerHealthyInventoryPath -Value @{
        Services = $names; CapturedAt = [DateTimeOffset]::UtcNow.ToString('o')
    }
}

function Write-DockerStateJson {
    param ([string]$Path, $Value)
    # Write alongside the destination so the final rename stays on one volume.
    # A killed writer leaves either the old complete state or the new one.
    $temporary = $Path + ".$PID.tmp"
    try {
        $Value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -ErrorAction Stop
        if (Test-Path -LiteralPath $Path) {
            [IO.File]::Replace($temporary, $Path, [NullString]::Value)
        } else { [IO.File]::Move($temporary, $Path) }
    } finally {
        Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
    }
}

function Request-DockerHostRecoveryReboot {
    param ([Parameter(Mandatory = $true)][string]$Reason)
    if (-not $script:DockerOperationLock -or -not (Test-CurrentProcessElevated)) {
        Write-DockerLog 'Host recovery reboot requires the operation lock and elevation.'
        return $false
    }
    if (-not (Test-DockerServiceOutage -Attempts 1)) {
        Write-DockerLog 'Host reboot withheld: independent service checks do not confirm a broad outage.'
        return $false
    }
    try {
        if (Test-Path -LiteralPath $DockerHostRebootPath) {
            $previous = Get-Content -LiteralPath $DockerHostRebootPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            $requested = [DateTimeOffset]::Parse($previous.RequestedAt)
            if ($previous.Status -ne 'rejected' -and [DateTimeOffset]::UtcNow -lt $requested.AddHours(6)) {
                Write-DockerLog 'Host recovery reboot suppressed: a reboot was already requested within six hours. Manual intervention is required if WSL remains unavailable.'
                return $false
            }
        }
        # Persist before requesting a restart so another task cannot create a reboot loop.
        $rebootState = @{ RequestedAt = [DateTimeOffset]::UtcNow.ToString('o'); Reason = $Reason; Status = 'pending' }
        Write-DockerStateJson -Path $DockerHostRebootPath -Value $rebootState
        $result = Invoke-ProcessWithTimeout -FilePath 'shutdown.exe' -Arguments @('/r', '/t', '30', '/d', 'p:4:1', '/c', 'Recover unresponsive WSL after bounded Docker recovery failed') -TimeoutSeconds 10
        if ($result.ExitCode -ne 0) {
            # A timeout is ambiguous: shutdown may already have been accepted.
            # Definite command rejection must not consume the six-hour cooldown.
            if ($result.ExitConfirmed -and $result.ExitCode -ne 124) {
                $rebootState.Status = 'rejected'
                Write-DockerStateJson -Path $DockerHostRebootPath -Value $rebootState
            }
            throw $result.Output
        }
        $script:DockerHostRebootRequested = $true
        Write-DockerLog "Controlled Windows recovery reboot scheduled in 30 seconds: $Reason"
        return $true
    } catch {
        Write-DockerLog "Unable to safely request host recovery reboot: $($_.Exception.Message)"
        return $false
    }
}

function Stop-DockerWslForRecovery {
    if (-not (Test-DockerServiceOutage -Attempts 1)) {
        Write-DockerLog 'WSL shutdown withheld: a service responded or the probe was inconclusive.'
        return $false
    }
    $shutdown = Invoke-ProcessWithTimeout -FilePath 'wsl.exe' -Arguments @('--shutdown') -TimeoutSeconds 90
    if ($shutdown.ExitCode -eq 124) {
        Write-DockerLog 'Normal WSL shutdown timed out; attempting one bounded forced WSL shutdown.'
        $shutdown = Invoke-ProcessWithTimeout -FilePath 'wsl.exe' -Arguments @('--shutdown', '--force') -TimeoutSeconds 60
    }
    if ($shutdown.ExitCode -ne 0) {
        Write-DockerLog "WSL shutdown failed; Docker will not be launched against the stuck VM. $($shutdown.Output)"
        if ($shutdown.ExitCode -eq 124) {
            Request-DockerHostRecoveryReboot -Reason 'Normal and forced WSL shutdown both timed out' | Out-Null
        }
        return $false
    }
    $probe = Invoke-WslCommand -Command 'true' -TimeoutSeconds 60 -MaxAttempts 1 -Quiet
    if ($probe.ExitCode -ne 0) {
        Write-DockerLog "WSL did not become usable after shutdown: $($probe.Output)"
        Request-DockerHostRecoveryReboot -Reason 'WSL remained unavailable after successful shutdown' | Out-Null
        return $false
    }
    return $true
}

function Invoke-DockerDesktopHardRecovery {
    param (
        [int]$TimeoutSeconds = 600,
        [switch]$ShutdownWsl
    )

    # Recheck after the startup wait. A missing integration socket must not kill
    # containers that have already resumed serving users.
    if (-not (Test-DockerAutomaticRecoveryAllowed)) { return $false }
    Write-DockerLog "Attempting hard Docker Desktop recovery. Elevated=$((Test-CurrentProcessElevated).ToString())."

    Invoke-DockerCliWithTimeout -Arguments @("desktop", "stop", "--timeout", "60") -TimeoutSeconds 90 -Quiet | Out-Null
    Stop-DockerDesktopProcessTree | Out-Null

    if ($ShutdownWsl) {
        Write-DockerLog "Shutting down WSL after stopping stale Docker Desktop processes."
        if (-not (Stop-DockerWslForRecovery)) { return $false }
    } else {
        Write-DockerLog "Terminating docker-desktop WSL distro after stopping stale Docker Desktop processes."
        $terminate = Invoke-ProcessWithTimeout -FilePath 'wsl.exe' -Arguments @('--terminate', 'docker-desktop') -TimeoutSeconds 90
        if ($terminate.ExitCode -ne 0) { return $false }
        Start-DockerRetrySleep -Seconds 5
    }

    Start-DockerDesktopServiceIfAvailable | Out-Null

    if (-not (Test-Path $DockerDesktopPath)) {
        Write-DockerLog "Docker Desktop executable not found at $DockerDesktopPath."
        return $false
    }

    Write-DockerLog "Launching Docker Desktop directly after hard recovery."
    Start-Process -FilePath $DockerDesktopPath -WindowStyle Hidden
    return Wait-DockerDesktopReady -TimeoutSeconds $TimeoutSeconds
}

function Invoke-WslCommand {
    param (
        [Parameter(Mandatory = $true)][string]$Command,
        [switch]$Quiet,
        [int]$TimeoutSeconds = 120,
        [ValidateRange(1, 5)][int]$MaxAttempts = 3,
        [int]$RetryDelaySeconds = 5
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $result = Invoke-ProcessWithTimeout -FilePath 'wsl.exe' -Arguments @('-e', 'bash', '-lc', $Command) -TimeoutSeconds $TimeoutSeconds -Quiet
        # Retry only explicit WSL connection/launch failures. An application
        # error or wrapper timeout could follow a partially completed mutation.
        $transportFailure = $result.ExitCode -ne 0 -and $result.Output -match 'Wsl/Service/(0x8007274c|0x800705b4|HCS_E_CONNECTION_TIMEOUT)'
        if (-not $transportFailure -or $attempt -eq $MaxAttempts) { break }
        Write-DockerLog "WSL transport failed on attempt $attempt/$MaxAttempts; retrying in $RetryDelaySeconds seconds."
        Start-DockerRetrySleep -Seconds $RetryDelaySeconds
    }
    if ($result.ExitCode -ne 0 -and -not $Quiet) {
        Write-DockerLog "WSL command failed with exit code $($result.ExitCode). Output: $($result.Output)"
    }
    return $result
}

function Invoke-WslDockerCompose {
    param (
        [Parameter(Mandatory = $true)][string]$ProjectPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Quiet
    )

    $argumentText = $Arguments -join ' '
    $composeCommand = "cd $ProjectPath && env_args=(); [ -f .env ] && env_args+=(--env-file .env); [ -f .env.secret ] && env_args+=(--env-file .env.secret); docker compose " + '"${env_args[@]}"' + " $argumentText"
    return Invoke-WslCommand -Command $composeCommand -TimeoutSeconds 300 -Quiet:$Quiet
}

function Invoke-WindowsDockerCompose {
    param (
        [Parameter(Mandatory = $true)][string]$ProjectPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Quiet
    )

    $envArgs = @()
    foreach ($envFile in @(".env", ".env.secret")) {
        $envPath = Join-Path $ProjectPath $envFile
        if (Test-Path $envPath) {
            $envArgs += @("--env-file", $envPath)
        }
    }

    $composeFile = Join-Path $ProjectPath "docker-compose.yml"
    $dockerArguments = @("compose") + $envArgs + @("--project-directory", $ProjectPath, "-f", $composeFile) + $Arguments
    return Invoke-DockerCli -Arguments $dockerArguments -TimeoutSeconds 300 -Quiet:$Quiet
}

function Get-WslComposeContainers {
    param ([switch]$All)
    $arguments = @('ps')
    if ($All) { $arguments += '--all' }
    $arguments += @('--format', '{{.Names}}|{{.Label "com.docker.compose.project.working_dir"}}|{{.State}}')
    $result = Invoke-DockerCli -Arguments $arguments -Quiet
    if ($result.ExitCode -ne 0) {
        throw "Cannot capture running Compose services through the Windows Docker CLI: $($result.Output)"
    }
    foreach ($line in ($result.Output -split "`n")) {
        $parts = $line.Trim() -split '\|', 3
        if ($parts.Count -ne 3 -or $parts[1] -cnotmatch '^/mnt/e/Docker/([a-zA-Z0-9][a-zA-Z0-9_.-]*)/?$') { continue }
        $project = $Matches[1]
        if ($project -eq 'cadvisor' -or -not (Test-Path (Join-Path $DockerProjectRoot "$project/docker-compose.yml"))) { continue }
        [pscustomobject]@{ Project = $project; Container = $parts[0]; Status = $parts[2] }
    }
}

function Get-RunningWslComposeServiceNames {
    return @(Get-WslComposeContainers | Select-Object -ExpandProperty Project | Sort-Object -Unique)
}

function Repair-WindowsComposeServices {
    param ([string[]]$ServiceNames = @("cadvisor"))

    foreach ($name in $ServiceNames) {
        if (-not $DockerWindowsComposeProjects.ContainsKey($name)) {
            Write-DockerLog "No Windows Compose project is configured for '$name'."
            return $false
        }

        $projectPath = $DockerWindowsComposeProjects[$name]
        Write-DockerLog "Recreating Windows compose service '$name' from $projectPath."
        $result = Invoke-WindowsDockerCompose -ProjectPath $projectPath -Arguments @("up", "-d", "--force-recreate")
        if ($result.ExitCode -ne 0) {
            Write-DockerLog "Windows compose repair failed for '$name'."
            return $false
        }

        if (-not (Wait-DockerContainerReady -Name $name -TimeoutSeconds 180)) {
            return $false
        }
    }

    return $true
}

function Repair-WslComposeBindServices {
    param (
        [string[]]$ServiceNames = @(),
        [int]$TimeoutSeconds = 1200,
        [switch]$OnlySpecified
    )

    $serviceSet = [ordered]@{}
    foreach ($name in $ServiceNames) {
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            $serviceSet[$name.Trim()] = $true
        }
    }

    if ($serviceSet.Count -eq 0 -and -not $OnlySpecified) {
        Write-DockerLog "No pre-restart WSL compose service list was captured; falling back to currently running compose services."
        try {
            foreach ($name in (Get-RunningWslComposeServiceNames)) { $serviceSet[$name] = $true }
        } catch {
            Write-DockerLog "Cannot repair mounts without a reliable service inventory: $($_.Exception.Message)"
            return $false
        }
    }

    if ($serviceSet.Count -eq 0) {
        Write-DockerLog "No running WSL compose services found for bind repair."
        return $true
    }

    $orderedNames = New-Object System.Collections.Generic.List[string]
    foreach ($name in $DockerWslBindRepairOrder) {
        if ($serviceSet.Contains($name)) {
            $orderedNames.Add($name)
            $serviceSet.Remove($name)
        }
    }
    foreach ($name in ($serviceSet.Keys | Sort-Object)) {
        $orderedNames.Add($name)
    }

    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    foreach ($name in $orderedNames) {
        if ((Get-Date) -ge $deadline) {
            Write-DockerLog "Timed out before WSL bind repair completed."
            return $false
        }

        if ($name -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$' -or -not (Test-Path (Join-Path $DockerProjectRoot "$name/docker-compose.yml"))) {
            Write-DockerLog "Cannot repair '$name'; a valid local Compose project is required."
            return $false
        }
        $projectPath = "/mnt/e/Docker/$name"
        Write-DockerLog "Recreating WSL compose service '$name' to refresh bind mounts."
        $composeResult = Invoke-WslDockerCompose -ProjectPath $projectPath -Arguments @("up", "-d", "--force-recreate")
        if ($name -eq "sunday-edge" -and $composeResult.ExitCode -eq 0) {
            $composeResult = Invoke-WslCommand -Command "python3 /mnt/e/Docker/scripts/sunday-edge-autoscale.py --reset-control" -TimeoutSeconds 180
        }
        if ($composeResult.ExitCode -ne 0) {
            Write-DockerLog "WSL bind repair failed for '$name'."
            return $false
        }
    }

    Write-DockerLog "WSL compose bind repair completed for $($orderedNames.Count) service(s)."
    return $true
}

function Get-StatefulServiceSentinelResult {
    param ([int]$MaxAttempts = 3)
    Write-DockerLog "Running stateful service sentinel checks."
    $result = Invoke-WslCommand -Command "bash /mnt/e/Scripts/docker-stateful-sentinel-check.sh" -TimeoutSeconds 90 -MaxAttempts $MaxAttempts -Quiet
    $failedServices = @($result.Output -split "`n" | ForEach-Object {
        if ($_ -match '^SENTINEL_FAIL ([a-zA-Z0-9][a-zA-Z0-9_.-]*)$') { $Matches[1] }
    } | Sort-Object -Unique)
    if ($result.ExitCode -eq 0) {
        Write-DockerLog "Stateful service sentinel checks passed."
    } else {
        Write-DockerLog "Stateful service sentinel checks failed. Output: $($result.Output)"
    }
    return [pscustomobject]@{ Healthy = ($result.ExitCode -eq 0); FailedServices = $failedServices; ExitCode = $result.ExitCode; Output = $result.Output }
}

function Test-StatefulServiceSentinels {
    return (Get-StatefulServiceSentinelResult).Healthy
}

function Get-DockerHealthSnapshot {
    $kind = 'Healthy'
    $failedServices = @()
    $detail = ''
    if (-not (Test-DockerDaemon)) {
        $kind = 'Daemon'
    } else {
        $transport = Invoke-WslCommand -Command 'true' -TimeoutSeconds 35 -MaxAttempts 1 -Quiet
        if ($transport.ExitCode -ne 0) {
            $kind = 'WslTransport'
            $detail = $transport.Output
        } elseif (-not (Test-WslDockerIntegration)) {
            $kind = 'WslIntegration'
            $detail = 'Windows Docker responds, but the native WSL Docker client cannot reach its engine.'
        } elseif (-not (Test-CriticalDockerReadiness)) {
            $kind = 'CriticalService'
        } else {
            $sentinel = Get-StatefulServiceSentinelResult -MaxAttempts 1
            if (-not $sentinel.Healthy) {
                $detail = $sentinel.Output
                if ($sentinel.ExitCode -eq 1 -and $sentinel.FailedServices.Count -gt 0) {
                    $kind = 'Sentinel'
                    $failedServices = $sentinel.FailedServices
                } else {
                    # An incomplete/failed probe is not evidence of bad mounts.
                    $transport = Invoke-WslCommand -Command 'true' -TimeoutSeconds 35 -MaxAttempts 1 -Quiet
                    $kind = if ($transport.ExitCode -ne 0) { 'WslTransport' } else { 'ProbeError' }
                }
            }
        }
    }
    return [pscustomobject]@{ Kind = $kind; FailedServices = $failedServices; Detail = $detail; Confirmed = $false }
}

function Get-ConfirmedDockerHealth {
    param ([ValidateRange(2, 5)][int]$Attempts = 3, [int]$RetryDelaySeconds = 10)
    $lastSignature = ''
    $consecutive = 0
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $health = Get-DockerHealthSnapshot
        if ($health.Kind -eq 'Healthy') { $health.Confirmed = $true; return $health }
        $signature = $health.Kind + '|' + ($health.FailedServices -join ',')
        if ($signature -eq $lastSignature) { $consecutive++ } else { $consecutive = 1 }
        $lastSignature = $signature
        Write-DockerLog "Health attempt $attempt/$Attempts failed: $signature. $($health.Detail)"
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds $RetryDelaySeconds }
    }
    $health.Confirmed = ($consecutive -eq $Attempts)
    return $health
}

function Start-UptimeKumaMaintenance {
    param (
        [int]$TtlMinutes = $DockerKumaMaintenanceTtlMinutes,
        [string]$Reason = "nightly-docker-desktop-restart",
        [switch]$AutoExpireOnly
    )

    $grafanaStarted = Start-GrafanaMaintenance -TtlMinutes $TtlMinutes -Reason $Reason

    Write-DockerLog "Creating Uptime Kuma maintenance window for Docker Desktop maintenance."
    if ($AutoExpireOnly) {
        Remove-Item -Path $DockerKumaMaintenanceIdPath -Force -ErrorAction SilentlyContinue
    }

    $command = "cd /mnt/e/Docker && python3 scripts/kuma-maintenance.py start --ttl-minutes $TtlMinutes --reason $Reason all"
    $result = Invoke-WslCommand -Command $command -TimeoutSeconds 45 -MaxAttempts 1
    if ($result.ExitCode -ne 0) {
        Write-DockerLog "Unable to create Uptime Kuma maintenance window; continuing maintenance."
        return $grafanaStarted
    }

    $maintenanceId = ($result.Output -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' } | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($maintenanceId)) {
        Write-DockerLog "Uptime Kuma maintenance helper did not return a maintenance id. Output: $($result.Output)"
        return $grafanaStarted
    }

    if ($AutoExpireOnly) {
        Write-DockerLog "Created Uptime Kuma maintenance window $maintenanceId; it will expire automatically after $TtlMinutes minutes."
        return $true
    }

    Set-Content -Path $DockerKumaMaintenanceIdPath -Value $maintenanceId
    Write-DockerLog "Created Uptime Kuma maintenance window $maintenanceId."
    return $true
}

function Stop-UptimeKumaMaintenance {
    Stop-GrafanaMaintenance
    if (-not (Test-Path $DockerKumaMaintenanceIdPath)) {
        return $true
    }

    $maintenanceId = Get-Content -Path $DockerKumaMaintenanceIdPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $maintenanceId) {
        $maintenanceId = $maintenanceId.Trim()
    }
    if ([string]::IsNullOrWhiteSpace($maintenanceId)) {
        Remove-Item -Path $DockerKumaMaintenanceIdPath -Force -ErrorAction SilentlyContinue
        return $true
    }

    Write-DockerLog "Removing Uptime Kuma maintenance window $maintenanceId."
    $command = "cd /mnt/e/Docker && python3 scripts/kuma-maintenance.py stop $maintenanceId"
    $result = Invoke-WslCommand -Command $command -TimeoutSeconds 45 -MaxAttempts 1
    Remove-Item -Path $DockerKumaMaintenanceIdPath -Force -ErrorAction SilentlyContinue

    if ($result.ExitCode -eq 0) {
        Write-DockerLog "Removed Uptime Kuma maintenance window $maintenanceId."
        return $true
    }

    Write-DockerLog "Unable to remove Uptime Kuma maintenance window $maintenanceId; it will expire automatically. Output: $($result.Output)"
    return $false
}

function Get-DockerComposeProjectPath {
    param ([Parameter(Mandatory = $true)][string]$Name)

    if ($DockerComposeProjects.ContainsKey($Name)) {
        return $DockerComposeProjects[$Name]
    }

    return $null
}

function Get-DockerDesktopStatus {
    $result = Invoke-DockerCli -Arguments @("desktop", "status", "--format", "json") -Quiet
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Output)) {
        return $null
    }

    try {
        return ($result.Output | ConvertFrom-Json).Status
    } catch {
        Write-DockerLog "Could not parse Docker Desktop status JSON: $($_.Exception.Message)"
        return $null
    }
}

function Test-DockerDaemon {
    $desktopStatus = Get-DockerDesktopStatus
    if ($desktopStatus -and $desktopStatus -ne "running") {
        Write-DockerLog "Docker Desktop status is '$desktopStatus'."
        return $false
    }

    $result = Invoke-DockerCli -Arguments @("info") -Quiet
    if ($result.ExitCode -eq 0) {
        return $true
    }

    Write-DockerLog "Docker daemon is not responding to 'docker info'. Output: $($result.Output)"
    return $false
}

function Wait-DockerDaemon {
    param (
        [int]$TimeoutSeconds = 300,
        [int]$IntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    Write-DockerLog "Waiting up to $TimeoutSeconds seconds for Docker Desktop and daemon readiness."

    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemon) {
            Write-DockerLog "Docker daemon is ready."
            return $true
        }
        Start-DockerRetrySleep -Seconds $IntervalSeconds
    }

    Write-DockerLog "Timed out waiting for Docker daemon readiness."
    return $false
}

function Test-WslDockerIntegration {
    # Docker Desktop's missing-integration CLI stub can exit zero. Require a
    # server-version marker from the native Linux client, not just an exit code.
    $command = 'test -S /var/run/docker.sock && test -x /usr/bin/docker && /usr/bin/docker info --format "WSL_DOCKER_READY={{.ServerVersion}}"'
    $result = Invoke-WslCommand -Command $command -TimeoutSeconds 20 -MaxAttempts 1 -Quiet
    return ($result.ExitCode -eq 0 -and $result.Output -match '(?m)^WSL_DOCKER_READY=\d+\.\d+\.\d+[^\r\n]*\r?$')
}

function Wait-WslDockerIntegration {
    param ([int]$TimeoutSeconds = 120, [int]$IntervalSeconds = 5)
    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    Write-DockerLog "Waiting up to $TimeoutSeconds seconds for native WSL Docker integration."
    do {
        if (Test-WslDockerIntegration) {
            Write-DockerLog 'Native WSL Docker integration is ready.'
            return $true
        }
        if ((Get-Date) -ge $deadline) { break }
        Start-DockerRetrySleep -Seconds $IntervalSeconds
    } while ((Get-Date) -lt $deadline)
    Write-DockerLog 'Native WSL Docker integration did not become ready; services will not be started.'
    return $false
}

function Wait-DockerDesktopReady {
    param ([int]$TimeoutSeconds = 180)
    if (-not (Wait-DockerDaemon -TimeoutSeconds $TimeoutSeconds)) { return $false }
    return Wait-WslDockerIntegration -TimeoutSeconds 120
}

function Get-DockerContainerState {
    param ([Parameter(Mandatory = $true)][string]$Name)

    $format = "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.ExitCode}}"
    $result = Invoke-DockerCli -Arguments @("inspect", "--format", $format, $Name) -Quiet
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Output)) {
        return $null
    }

    $parts = $result.Output.Trim() -split "\|", 3
    return [pscustomobject]@{
        Name = $Name
        Status = $parts[0]
        Health = $parts[1]
        ExitCode = if ($parts.Count -ge 3) { $parts[2] } else { "" }
    }
}

function Test-DockerContainerReady {
    param (
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$Quiet
    )

    $state = Get-DockerContainerState -Name $Name
    if (-not $state) {
        if (-not $Quiet) { Write-DockerLog "Container '$Name' does not exist." }
        return $false
    }

    if ($state.Status -ne "running") {
        if (-not $Quiet) { Write-DockerLog "Container '$Name' is '$($state.Status)' instead of running. ExitCode=$($state.ExitCode)." }
        return $false
    }

    if ($state.Health -ne "none" -and $state.Health -ne "healthy") {
        if (-not $Quiet) { Write-DockerLog "Container '$Name' health is '$($state.Health)'." }
        return $false
    }

    return $true
}

function Wait-DockerContainerReady {
    param (
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$TimeoutSeconds = 180,
        [int]$IntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerContainerReady -Name $Name -Quiet) {
            Write-DockerLog "Container '$Name' is ready."
            return $true
        }
        Start-DockerRetrySleep -Seconds $IntervalSeconds
    }

    Test-DockerContainerReady -Name $Name | Out-Null
    Write-DockerLog "Timed out waiting for container '$Name' readiness."
    return $false
}

function Stop-DockerContainerIfPresent {
    param (
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$TimeoutSeconds = 60
    )

    $projectPath = Get-DockerComposeProjectPath -Name $Name
    if ($projectPath) {
        Write-DockerLog "Stopping service '$Name' via WSL docker compose in $projectPath."
        $composeResult = Invoke-WslDockerCompose -ProjectPath $projectPath -Arguments @("stop", $Name)
        return ($composeResult.ExitCode -eq 0)
    }

    $state = Get-DockerContainerState -Name $Name
    if (-not $state) {
        Write-DockerLog "Container '$Name' does not exist; nothing to stop."
        return $true
    }

    if ($state.Status -ne "running") {
        Write-DockerLog "Container '$Name' is already '$($state.Status)'."
        return $true
    }

    Write-DockerLog "Stopping container '$Name'."
    $result = Invoke-DockerCli -Arguments @("stop", "--time", $TimeoutSeconds.ToString(), $Name) -TimeoutSeconds ($TimeoutSeconds + 30)
    return ($result.ExitCode -eq 0)
}

function Start-DockerContainerIfPresent {
    param ([Parameter(Mandatory = $true)][string]$Name)

    $state = Get-DockerContainerState -Name $Name
    if ($state -and $state.Status -eq 'running') { return $true }
    $projectPath = Get-DockerComposeProjectPath -Name $Name
    if ($projectPath) {
        Write-DockerLog "Starting service '$Name' via WSL docker compose in $projectPath."
        $composeResult = Invoke-WslDockerCompose -ProjectPath $projectPath -Arguments @("up", "-d", $Name)
        return ($composeResult.ExitCode -eq 0)
    }

    $state = Get-DockerContainerState -Name $Name
    if (-not $state) {
        Write-DockerLog "Container '$Name' does not exist; cannot start it."
        return $false
    }

    if ($state.Status -eq "running") {
        return $true
    }

    Write-DockerLog "Starting container '$Name'."
    $result = Invoke-DockerCli -Arguments @("start", $Name)
    return ($result.ExitCode -eq 0)
}

function Restart-DockerContainerAndWait {
    param (
        [Parameter(Mandatory = $true)][string]$Name,
        [int]$StopTimeoutSeconds = 60,
        [int]$ReadyTimeoutSeconds = 180
    )

    $projectPath = Get-DockerComposeProjectPath -Name $Name
    if ($projectPath) {
        Write-DockerLog "Restarting service '$Name' via WSL docker compose in $projectPath."
        $composeResult = Invoke-WslDockerCompose -ProjectPath $projectPath -Arguments @("restart", $Name)
        if ($composeResult.ExitCode -ne 0) {
            Write-DockerLog "Compose restart failed for '$Name'; trying compose up -d."
            $composeResult = Invoke-WslDockerCompose -ProjectPath $projectPath -Arguments @("up", "-d", $Name)
        }

        if ($composeResult.ExitCode -ne 0) {
            return $false
        }
    } else {
        Write-DockerLog "Restarting container '$Name'."
        $result = Invoke-DockerCli -Arguments @("restart", "--time", $StopTimeoutSeconds.ToString(), $Name) -TimeoutSeconds ($StopTimeoutSeconds + 30)
        if ($result.ExitCode -ne 0) {
            return $false
        }
    }

    return Wait-DockerContainerReady -Name $Name -TimeoutSeconds $ReadyTimeoutSeconds
}

function Test-RequiredDockerNetwork {
    param ([Parameter(Mandatory = $true)][string]$Name)

    $result = Invoke-DockerCli -Arguments @("network", "inspect", $Name) -Quiet
    if ($result.ExitCode -eq 0) {
        return $true
    }

    Write-DockerLog "Required Docker network '$Name' is missing or inaccessible."
    return $false
}

function Test-ContainerUrl {
    param (
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 5,
        [switch]$Quiet
    )

    $result = Invoke-DockerCli -Arguments @("exec", $ContainerName, "curl", "-fsS", "--max-time", $TimeoutSeconds.ToString(), "-o", "/dev/null", $Url) -Quiet
    if ($result.ExitCode -eq 0) {
        return $true
    }

    if (-not $Quiet) {
        Write-DockerLog "Container probe failed from '$ContainerName' to '$Url'. Output: $($result.Output)"
    }
    return $false
}

function Wait-ContainerUrl {
    param (
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    while ((Get-Date) -lt $deadline) {
        if (Test-ContainerUrl -ContainerName $ContainerName -Url $Url -Quiet) {
            Write-DockerLog "Container probe succeeded from '$ContainerName' to '$Url'."
            return $true
        }
        Start-DockerRetrySleep -Seconds $IntervalSeconds
    }

    Test-ContainerUrl -ContainerName $ContainerName -Url $Url | Out-Null
    return $false
}

function Test-HostUrl {
    param (
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 5,
        [switch]$Quiet
    )

    $TimeoutSeconds = Get-DockerTimeoutSeconds -Requested $TimeoutSeconds
    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds | Out-Null
        return $true
    } catch {
        if (-not $Quiet) {
            Write-DockerLog "Host probe failed for '$Url'. Error: $($_.Exception.Message)"
        }
        return $false
    }
}

function Wait-HostUrl {
    param (
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    while ((Get-Date) -lt $deadline) {
        if (Test-HostUrl -Url $Url -Quiet) {
            Write-DockerLog "Host probe succeeded for '$Url'."
            return $true
        }
        Start-DockerRetrySleep -Seconds $IntervalSeconds
    }

    Test-HostUrl -Url $Url | Out-Null
    return $false
}

function Test-TcpPort {
    param (
        [string]$HostName = "127.0.0.1",
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutMilliseconds = 3000,
        [switch]$Quiet
    )

    $TimeoutMilliseconds = [Math]::Min($TimeoutMilliseconds, 1000 * (Get-DockerTimeoutSeconds -Requested ([int][Math]::Ceiling($TimeoutMilliseconds / 1000))))
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            if (-not $Quiet) { Write-DockerLog "TCP probe timed out for $HostName`:$Port." }
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        if (-not $Quiet) { Write-DockerLog "TCP probe failed for $HostName`:$Port. Error: $($_.Exception.Message)" }
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-TcpPort {
    param (
        [string]$HostName = "127.0.0.1",
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds((Get-DockerTimeoutSeconds -Requested $TimeoutSeconds))
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port -Quiet) {
            Write-DockerLog "TCP probe succeeded for $HostName`:$Port."
            return $true
        }
        Start-DockerRetrySleep -Seconds $IntervalSeconds
    }

    Test-TcpPort -HostName $HostName -Port $Port | Out-Null
    return $false
}

function Test-PlexInternal {
    return Test-ContainerUrl -ContainerName "plex" -Url "http://127.0.0.1:32400/identity"
}

function Repair-PlexHostPort {
    param ([switch]$RestartOnFailure)

    $internalOk = Test-ContainerUrl -ContainerName "plex" -Url "http://127.0.0.1:32400/identity" -Quiet
    $hostOk = Test-HostUrl -Url "http://127.0.0.1:32400/identity" -Quiet

    if ($internalOk -and $hostOk) {
        Write-DockerLog "Plex internal and host port probes are healthy."
        return $true
    }

    if (-not $internalOk) {
        Write-DockerLog "Plex internal probe failed."
        return $false
    }

    Write-DockerLog "Plex internal probe works, but host port 32400 failed."
    if (-not $RestartOnFailure) {
        return $false
    }

    if (-not (Test-DockerServiceOutage -ServiceNames @('plex'))) {
        Write-DockerLog 'Plex restart withheld: host/LAN checks do not confirm sustained Plex unavailability.'
        return $false
    }

    if (-not (Restart-DockerContainerAndWait -Name "plex" -StopTimeoutSeconds 90 -ReadyTimeoutSeconds 240)) {
        return $false
    }

    if (-not (Wait-ContainerUrl -ContainerName "plex" -Url "http://127.0.0.1:32400/identity" -TimeoutSeconds 180)) {
        return $false
    }

    return Wait-HostUrl -Url "http://127.0.0.1:32400/identity" -TimeoutSeconds 120
}

function Test-SwagDependencyEndpoints {
    $socketOk = Test-ContainerUrl -ContainerName "swag" -Url "http://socket-proxy:2375/_ping" -Quiet
    $uptimeOk = Test-ContainerUrl -ContainerName "swag" -Url "http://uptime-kuma:3001/" -Quiet
    $plexOk = Test-ContainerUrl -ContainerName "swag" -Url "http://plex:32400/identity" -Quiet

    if ($socketOk -and $uptimeOk -and $plexOk) {
        Write-DockerLog "SWAG dependency probes are healthy."
        return $true
    }

    Write-DockerLog "SWAG dependency probe status: socket-proxy=$socketOk uptime-kuma=$uptimeOk plex=$plexOk"
    return $false
}

function Start-CriticalDockerServices {
    param ([int]$TimeoutSeconds = 480)
    $DockerCriticalTimer = [Diagnostics.Stopwatch]::StartNew()
    $DockerCriticalBudgetSeconds = $TimeoutSeconds
    try { return Start-CriticalDockerServicesCore }
    catch [TimeoutException] {
        Write-DockerLog "Critical startup exceeded its $TimeoutSeconds-second budget; deferring remaining work."
        return $false
    }
}

function Start-CriticalDockerServicesCore {

    if (-not (Test-DockerDaemon)) { return $false }
    if (-not (Wait-WslDockerIntegration)) { return $false }
    if (-not (Test-RequiredDockerNetwork -Name "socket-proxy-net")) { return $false }
    if (-not (Test-RequiredDockerNetwork -Name "proxynet")) { return $false }

    Write-DockerLog "Starting critical containers in dependency order."

    if (-not (Start-DockerContainerIfPresent -Name "socket-proxy")) { return $false }
    if (-not (Wait-DockerContainerReady -Name "socket-proxy" -TimeoutSeconds 180)) { return $false }

    if (-not (Start-DockerContainerIfPresent -Name "uptime-kuma")) { return $false }
    if (-not (Wait-DockerContainerReady -Name "uptime-kuma" -TimeoutSeconds 180)) { return $false }
    if (-not (Wait-ContainerUrl -ContainerName "uptime-kuma" -Url "http://localhost:3001/" -TimeoutSeconds 180)) { return $false }
    if (-not (Wait-ContainerUrl -ContainerName "uptime-kuma" -Url "http://uptime-kuma:3001/" -TimeoutSeconds 60)) { return $false }

    if (-not (Start-DockerContainerIfPresent -Name "plex")) { return $false }
    if (-not (Wait-DockerContainerReady -Name "plex" -TimeoutSeconds 240)) { return $false }
    if (-not (Wait-ContainerUrl -ContainerName "plex" -Url "http://127.0.0.1:32400/identity" -TimeoutSeconds 240)) { return $false }
    if (-not (Repair-PlexHostPort -RestartOnFailure)) { return $false }

    if (-not (Start-DockerContainerIfPresent -Name "swag")) { return $false }
    if (-not (Wait-DockerContainerReady -Name "swag" -TimeoutSeconds 240)) { return $false }
    if (-not (Test-SwagDependencyEndpoints)) {
        Write-DockerLog "Restarting SWAG now that dependencies are ready."
        if (-not (Restart-DockerContainerAndWait -Name "swag" -StopTimeoutSeconds 90 -ReadyTimeoutSeconds 240)) { return $false }
        if (-not (Test-SwagDependencyEndpoints)) { return $false }
    }

    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 80 -TimeoutSeconds 120)) { return $false }
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 443 -TimeoutSeconds 120)) { return $false }

    Write-DockerLog "Critical Docker services are ready."
    return $true
}

function Test-CriticalDockerReadiness {
    param ([switch]$Repair)

    if (-not (Test-DockerDaemon)) { return $false }

    if ($Repair) {
        return Start-CriticalDockerServices
    }

    foreach ($network in @("socket-proxy-net", "proxynet")) {
        if (-not (Test-RequiredDockerNetwork -Name $network)) { return $false }
    }

    foreach ($container in @("socket-proxy", "uptime-kuma", "plex", "swag")) {
        if (-not (Test-DockerContainerReady -Name $container)) { return $false }
    }

    if (-not (Test-ContainerUrl -ContainerName "uptime-kuma" -Url "http://uptime-kuma:3001/" -Quiet)) { return $false }
    if (-not (Test-ContainerUrl -ContainerName "plex" -Url "http://127.0.0.1:32400/identity" -Quiet)) { return $false }
    if (-not (Test-HostUrl -Url "http://127.0.0.1:32400/identity" -Quiet)) { return $false }
    if (-not (Test-SwagDependencyEndpoints)) { return $false }
    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 80 -Quiet)) { return $false }
    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 443 -Quiet)) { return $false }

    return $true
}

function Restart-DockerDesktopClean {
    param (
        [int]$TimeoutSeconds = 600,
        [switch]$ShutdownWslOnFallback
    )

    if (-not (Test-DockerServiceOutage -Attempts 1)) {
        Write-DockerLog 'Desktop restart withheld: service availability changed before recovery.'
        return $false
    }
    Write-DockerLog "Restarting Docker Desktop with Docker Desktop CLI."
    $cliRestartSeconds = [Math]::Min($TimeoutSeconds, 180)
    $cliTimeoutSeconds = $cliRestartSeconds + 30
    $readinessTimeoutSeconds = $TimeoutSeconds
    $restart = Invoke-DockerCliWithTimeout -Arguments @("desktop", "restart", "--timeout", $cliRestartSeconds.ToString()) -TimeoutSeconds $cliTimeoutSeconds
    # A CLI error can still leave a healthy engine. Observe before escalating.
    if (Wait-DockerDesktopReady -TimeoutSeconds $readinessTimeoutSeconds) {
        return $true
    }

    Write-DockerLog "Docker Desktop or WSL integration did not become ready after CLI restart path; switching to hard recovery."
    return Invoke-DockerDesktopHardRecovery -TimeoutSeconds $TimeoutSeconds -ShutdownWsl:$ShutdownWslOnFallback
}
