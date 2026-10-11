param ([switch]$LiveReadOnly, [string]$ProjectRoot = (Split-Path (Split-Path $PSScriptRoot)))
$ErrorActionPreference = 'Stop'
$suiteRoot = $PSScriptRoot
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('docker-watchdog-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
$script:passed = 0
$script:failed = 0

function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Health([string]$Kind = 'Healthy', [bool]$Confirmed = $true, [string[]]$Names = @()) {
    [pscustomobject]@{ Kind=$Kind; Confirmed=$Confirmed; FailedServices=$Names; Detail='' }
}

function Run-Test([string]$Name, [scriptblock]$Body) {
    try {
        & {
            . (Join-Path $suiteRoot 'docker-desktop-common.ps1') -ProjectRoot $ProjectRoot
            $realMaintenanceStart = ${function:Start-UptimeKumaMaintenance}
            $tokens = $null; $errors = $null
            $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $suiteRoot 'start-docker-desktop.ps1'), [ref]$tokens, [ref]$errors)
            foreach ($definition in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
                . ([scriptblock]::Create($definition.Extent.Text))
            }
            $DockerLogFilePath = Join-Path $scratch 'test.log'
            $logFilePath = Join-Path $scratch 'restart-test.log'
            $DockerOperationLockPath = Join-Path $scratch 'operation.lock'
            $DockerRecoveryInventoryPath = Join-Path $scratch 'recovery-services.json'
            $DockerHostRebootPath = Join-Path $scratch 'host-reboot.json'
            Remove-Item -LiteralPath $DockerRecoveryInventoryPath,$DockerHostRebootPath -ErrorAction SilentlyContinue
            $DockerProjectRoot = Join-Path $scratch 'projects'
            $maxRestartAttempts = 3; $restartCooldownMinutes = 10; $restartWindowMinutes = 60
            $script:events = @(); $script:calls = 0
            Set-Content $logFilePath ''
            function Write-DockerLog { param($Message) }
            function Write-Log { param($message) }
            function Clean-LogFile {}
            function Test-MaintenanceWindow { $false }
            function Send-DiscordAlert { param($title,$description,$color) $script:events += 'alert' }
            function Start-UptimeKumaMaintenance { param($Reason) $script:events += 'maintenance-start'; $true }
            function Stop-UptimeKumaMaintenance { $script:events += 'maintenance-stop'; $true }
            function Invoke-WslDockerCompose { throw 'Unexpected real Compose mutation in test' }
            $realIntegrationProbe = ${function:Test-WslDockerIntegration}
            $realIntegrationWait = ${function:Wait-WslDockerIntegration}
            $realAvailability = ${function:Get-DockerServiceAvailability}
            $realOutage = ${function:Test-DockerServiceOutage}
            $realRecoveryAllowed = ${function:Test-DockerAutomaticRecoveryAllowed}
            $realPendingTargets = ${function:Get-DockerPendingRecoveryTargets}
            function Test-WslDockerIntegration { $true }
            function Wait-WslDockerIntegration { $true }
            function Test-DockerServiceOutage { $true }
            function Test-DockerAutomaticRecoveryAllowed { $true }
            function Get-DockerPendingRecoveryTargets { param($ServiceNames) [pscustomobject]@{Valid=$true;Services=$ServiceNames} }
            & $Body
        }
        $script:passed++
        Write-Host "PASS $Name"
    } catch {
        $script:failed++
        Write-Host "FAIL $Name`: $($_.Exception.Message) at $($_.ScriptStackTrace)"
    }
}

Run-Test 'process preserves stdout, stderr and exit zero' {
    $r = Invoke-ProcessWithTimeout -FilePath powershell.exe -Arguments @('-NoProfile','-Command','[Console]::Out.WriteLine("out ok"); [Console]::Error.WriteLine("err ok"); exit 0') -Quiet
    Assert-True ($r.ExitCode -eq 0 -and $r.Output -match 'out ok' -and $r.Output -match 'err ok') ($r | ConvertTo-Json -Compress)
}
Run-Test 'process preserves nonzero exit code' {
    $r = Invoke-ProcessWithTimeout -FilePath powershell.exe -Arguments @('-NoProfile','-Command','exit 7') -Quiet
    Assert-True ($r.ExitCode -eq 7) "Expected 7, got $($r.ExitCode)"
}
Run-Test 'process handles empty output' {
    $r = Invoke-ProcessWithTimeout -FilePath powershell.exe -Arguments @('-NoProfile','-Command','exit 0') -Quiet
    Assert-True ($r.ExitCode -eq 0 -and $r.Output -eq '') ($r | ConvertTo-Json -Compress)
}
Run-Test 'process timeout is bounded and returns 124' {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-ProcessWithTimeout -FilePath powershell.exe -Arguments @('-NoProfile','-Command','Start-Sleep -Seconds 15') -TimeoutSeconds 1 -Quiet
    Assert-True ($r.ExitCode -eq 124 -and $clock.Elapsed.TotalSeconds -lt 8) ($r | ConvertTo-Json -Compress)
}
Run-Test 'WSL retries connection errors then succeeds' {
    function Invoke-ProcessWithTimeout {
        $script:calls++
        if ($script:calls -lt 3) { [pscustomobject]@{ExitCode=-1;Output='Wsl/Service/0x8007274c'} }
        else { [pscustomobject]@{ExitCode=0;Output='ok'} }
    }
    $r = Invoke-WslCommand -Command 'true' -RetryDelaySeconds 0
    Assert-True ($r.ExitCode -eq 0 -and $script:calls -eq 3) 'Transport retries incorrect'
}
Run-Test 'WSL never retries a possible partial mutation' {
    function Invoke-ProcessWithTimeout { $script:calls++; [pscustomobject]@{ExitCode=124;Output='Timed out after 1 seconds'} }
    $r = Invoke-WslCommand -Command 'test' -RetryDelaySeconds 0
    Assert-True ($r.ExitCode -eq 124 -and $script:calls -eq 1) 'Timed-out mutation was retried'
}
Run-Test 'WSL never retries application errors' {
    function Invoke-ProcessWithTimeout { $script:calls++; [pscustomobject]@{ExitCode=1;Output='SENTINEL_FAIL homepage'} }
    $r = Invoke-WslCommand -Command 'test' -RetryDelaySeconds 0
    Assert-True ($r.ExitCode -eq 1 -and $script:calls -eq 1) 'Application failure was retried'
}
Run-Test 'failed inventory is distinguishable from empty inventory' {
    function Invoke-DockerCli { [pscustomobject]@{ExitCode=1;Output='unavailable'} }
    $threw = $false
    try { Get-RunningWslComposeServiceNames | Out-Null } catch { $threw = $true }
    Assert-True $threw 'Failed inventory did not throw'
    Assert-True (-not (Repair-WslComposeBindServices)) 'Unknown inventory was reported repaired'
}
Run-Test 'inventory uses Windows and filters known projects and cAdvisor' {
    foreach ($name in @('homepage','plex','cadvisor','mod-mc')) {
        New-Item -ItemType Directory -Path (Join-Path $DockerProjectRoot $name) -Force | Out-Null
        Set-Content (Join-Path $DockerProjectRoot "$name/docker-compose.yml") 'services: {}'
    }
    function Invoke-DockerCli {
        [pscustomobject]@{ExitCode=0;Output="plex|/mnt/e/Docker/plex|running`nhomepage|/mnt/e/Docker/homepage|running`ncadvisor|E:\Docker\cadvisor|running`nunknown||running`nmod-mc-minecraft-server-1|/mnt/e/Docker/mod-mc|running`nmod-mc-sidecar-1|/mnt/e/Docker/mod-mc|running`nexternal|/tmp/mod-mc|running"}
    }
    function Invoke-WslCommand { throw 'Inventory must not use WSL' }
    $names = @(Get-RunningWslComposeServiceNames)
    Assert-True (($names -join ',') -eq 'homepage,mod-mc,plex') "Unexpected inventory: $names"
}
Run-Test 'empty targeted repair never discovers or recreates all services' {
    function Get-RunningWslComposeServiceNames { throw 'Unexpected discovery' }
    Assert-True (Repair-WslComposeBindServices -ServiceNames @() -OnlySpecified) 'Empty repair failed'
}
Run-Test 'targeted repair respects order and surfaces Compose failure' {
    function Invoke-WslDockerCompose { param($ProjectPath,$Arguments) $script:events += $ProjectPath; [pscustomobject]@{ExitCode=1;Output='failed'} }
    $ok = Repair-WslComposeBindServices -ServiceNames @('homepage','plex') -OnlySpecified
    Assert-True (-not $ok -and ($script:events -join ',') -eq '/mnt/e/Docker/plex') 'Unexpected repair ordering or hidden failure'
}
Run-Test 'healthy containers do not invoke Compose up' {
    function Get-DockerContainerState { [pscustomobject]@{Status='running'} }
    Assert-True (Start-DockerContainerIfPresent -Name plex) 'Healthy container was not accepted'
}
Run-Test 'transport probe failure is classified separately' {
    function Test-DockerDaemon { $true }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=-1;Output='WSL timeout'} }
    function Test-CriticalDockerReadiness { throw 'Should not run after failed transport' }
    Assert-True ((Get-DockerHealthSnapshot).Kind -eq 'WslTransport') 'Wrong failure category'
}
Run-Test 'incomplete sentinel check is never a mount failure' {
    function Test-DockerDaemon { $true }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output=''} }
    function Test-CriticalDockerReadiness { $true }
    function Get-StatefulServiceSentinelResult { [pscustomobject]@{Healthy=$false;ExitCode=124;FailedServices=@('homepage');Output='timeout'} }
    Assert-True ((Get-DockerHealthSnapshot).Kind -eq 'ProbeError') 'Incomplete check could recreate services'
}
Run-Test 'transient health failure recovers without confirmation' {
    function Get-DockerHealthSnapshot { $script:calls++; if ($script:calls -eq 1) { Health WslTransport $false } else { Health } }
    $h = Get-ConfirmedDockerHealth -RetryDelaySeconds 0
    Assert-True ($h.Kind -eq 'Healthy' -and $script:calls -eq 2) 'Transient failure did not recover'
}
Run-Test 'three identical failures are required' {
    function Get-DockerHealthSnapshot { $script:calls++; Health WslTransport $false }
    $h = Get-ConfirmedDockerHealth -RetryDelaySeconds 0
    Assert-True ($h.Confirmed -and $script:calls -eq 3) 'Persistent failure not confirmed correctly'
}
Run-Test 'changing failure categories cannot trigger recovery' {
    function Get-DockerHealthSnapshot { $script:calls++; Health (@('Sentinel','CriticalService','Daemon')[$script:calls-1]) $false }
    Assert-True (-not (Get-ConfirmedDockerHealth -RetryDelaySeconds 0).Confirmed) 'Mixed failures were marked persistent'
}
Run-Test 'healthy watchdog never mutates services or sends alerts' {
    function Get-ConfirmedDockerHealth { Health }
    function Restart-DockerDesktop { throw 'Unexpected Desktop restart' }
    $code = Invoke-DockerHealthMonitor
    Assert-True ($code -eq 0 -and $script:events.Count -eq 0) 'Healthy path has side effects'
}
Run-Test 'application failure gets targeted repair and never restarts Desktop' {
    function Get-ConfirmedDockerHealth { Health Sentinel $true @('homepage') }
    function Repair-WslComposeBindServices { param($ServiceNames,[switch]$OnlySpecified) Assert-True ($OnlySpecified -and ($ServiceNames -join ',') -eq 'homepage') 'Not targeted'; $script:events += 'repair-homepage'; $false }
    function Restart-DockerDesktop { throw 'Application failure restarted Desktop' }
    $code = Invoke-DockerHealthMonitor
    Assert-True ($code -eq 1 -and ($script:events -join ',') -eq 'maintenance-start,repair-homepage,maintenance-stop') "Unexpected actions: $script:events"
}
Run-Test 'persistent critical service failure never restarts healthy Desktop' {
    function Get-ConfirmedDockerHealth { Health CriticalService }
    function Start-CriticalDockerServices { $script:events += 'ordered-repair'; $false }
    function Restart-DockerDesktop { throw 'Critical service failure restarted Desktop' }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Should report degraded'
    Assert-True ($script:events -contains 'ordered-repair') 'Repair not attempted'
}
Run-Test 'persistent daemon failure follows the full recovery path' {
    function Get-ConfirmedDockerHealth { Health Daemon }
    function Get-DockerHealthSnapshot { Health Daemon }
    function Test-DockerRestartAllowed { $true }
    function Restart-DockerDesktop { $script:events += 'desktop-restart'; $true }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 0) 'Recovery failed'
    Assert-True (($script:events -join ',') -eq 'alert,desktop-restart,alert') 'Unexpected recovery actions'
}
Run-Test 'cooldown and hourly restart limit prevent restart loops' {
    Set-Content $logFilePath ''
    Assert-True (Test-DockerRestartAllowed) 'Fresh watchdog should allow recovery'
    Set-Content $logFilePath "$((Get-Date).AddMinutes(-2).ToString('yyyy-MM-dd HH:mm:ss')) - === RESTARTING DOCKER DESKTOP ==="
    Assert-True (-not (Test-DockerRestartAllowed)) 'Cooldown missing'
    @(15,30,45) | ForEach-Object { "$((Get-Date).AddMinutes(-$_).ToString('yyyy-MM-dd HH:mm:ss')) - === RESTARTING DOCKER DESKTOP ===" } | Set-Content $logFilePath
    Assert-True (-not (Test-DockerRestartAllowed)) 'Hourly cap missing'
}
Run-Test 'successful CLI restart never invokes stop fallback' {
    function Invoke-DockerCliWithTimeout { param($Arguments) $script:events += ($Arguments -join ' '); [pscustomobject]@{ExitCode=0;Output='success'} }
    function Wait-DockerDesktopReady { $true }
    Assert-True (Restart-DockerDesktopClean) 'Recovery failed'
    Assert-True ($script:events.Count -eq 1 -and $script:events[0] -match '^desktop restart') 'Redundant stop/start'
}
Run-Test 'service repair cooldown prevents repeated application restarts' {
    $h = Health Sentinel $true @('homepage')
    Set-Content $logFilePath "$((Get-Date).AddMinutes(-2).ToString('yyyy-MM-dd HH:mm:ss')) - === REPAIRING DOCKER SERVICES === Sentinel|homepage"
    Assert-True (-not (Test-DockerServiceRepairAllowed -Health $h)) 'Service cooldown missing'
    Assert-True (Test-DockerServiceRepairAllowed -Health (Health Sentinel $true @('plex'))) 'Unrelated repair blocked'
}
Run-Test 'failed CLI and unhealthy daemon use one hard recovery' {
    function Invoke-DockerCliWithTimeout {
        param($Arguments)
        $script:events += ($Arguments -join ' ')
        [pscustomobject]@{ExitCode=$(if ($Arguments[1] -eq 'restart') { 1 } else { 0 });Output=''}
    }
    function Wait-DockerDesktopReady { $false }
    function Invoke-DockerDesktopHardRecovery { $script:events += 'hard-recovery'; $true }
    Assert-True (Restart-DockerDesktopClean) 'Fallback recovery failed'
    Assert-True ($script:events.Count -eq 2 -and $script:events[1] -eq 'hard-recovery') 'Repeated stop/start fallback'
}
Run-Test 'successful WSL shutdown never forces or reboots' {
    function Invoke-ProcessWithTimeout { param($FilePath,$Arguments) $script:events += ($Arguments -join ' '); [pscustomobject]@{ExitCode=0;Output=''} }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output=''} }
    function Request-DockerHostRecoveryReboot { throw 'Unexpected reboot' }
    Assert-True (Stop-DockerWslForRecovery) 'Clean WSL shutdown failed'
    Assert-True (($script:events -join ',') -eq '--shutdown') 'Forced a healthy WSL VM'
}
Run-Test 'hung normal WSL shutdown gets one forced attempt' {
    function Invoke-ProcessWithTimeout { param($FilePath,$Arguments) $script:events += ($Arguments -join ' '); [pscustomobject]@{ExitCode=$(if ($Arguments.Count -eq 1) {124} else {0});Output=''} }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output=''} }
    function Request-DockerHostRecoveryReboot { throw 'Unexpected reboot' }
    Assert-True (Stop-DockerWslForRecovery) 'Forced shutdown recovery failed'
    Assert-True (($script:events -join ',') -eq '--shutdown,--shutdown --force') 'Incorrect escalation order'
}
Run-Test 'two hung WSL shutdowns request host recovery and stop Docker launch' {
    function Invoke-ProcessWithTimeout { [pscustomobject]@{ExitCode=124;Output='timeout'} }
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=1;Output='unavailable'} }
    function Stop-DockerDesktopProcessTree { $true }
    function Request-DockerHostRecoveryReboot { param($Reason) $script:events += 'reboot'; $true }
    function Start-DockerDesktopServiceIfAvailable { throw 'Started Docker after failed WSL shutdown' }
    Assert-True (-not (Invoke-DockerDesktopHardRecovery -ShutdownWsl)) 'Reported recovery while reboot was pending'
    Assert-True (($script:events -join ',') -eq 'reboot') 'Host recovery was skipped or repeated'
}
Run-Test 'ordinary WSL command errors do not reboot the host' {
    function Invoke-ProcessWithTimeout { [pscustomobject]@{ExitCode=1;Output='unsupported option'} }
    function Request-DockerHostRecoveryReboot { throw 'Unexpected reboot for command error' }
    Assert-True (-not (Stop-DockerWslForRecovery)) 'WSL error ignored'
}
Run-Test 'unusable WSL after successful shutdown requests host recovery' {
    function Invoke-ProcessWithTimeout { [pscustomobject]@{ExitCode=0;Output=''} }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=1;Output='HCS/ERROR_SHARING_VIOLATION'} }
    function Request-DockerHostRecoveryReboot { param($Reason) $script:events += 'reboot'; $true }
    Assert-True (-not (Stop-DockerWslForRecovery)) 'Unusable WSL accepted'
    Assert-True (($script:events -join ',') -eq 'reboot') 'Host recovery missing'
}
Run-Test 'host reboot journal prevents repeated reboots and expires after six hours' {
    $script:DockerOperationLock = [pscustomobject]@{}
    function Test-CurrentProcessElevated { $true }
    function Invoke-ProcessWithTimeout { param($FilePath,$Arguments) Assert-True ($FilePath -eq 'shutdown.exe') 'Unexpected command'; $script:calls++; [pscustomobject]@{ExitCode=0;Output=''} }
    Assert-True (Request-DockerHostRecoveryReboot -Reason test) 'First request failed'
    Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Repeated reboot allowed'
    Assert-True ($script:calls -eq 1) 'Cooldown still invoked shutdown'
    @{ RequestedAt = [DateTimeOffset]::UtcNow.AddHours(-7).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $DockerHostRebootPath
    Assert-True (Request-DockerHostRecoveryReboot -Reason test) 'Expired cooldown did not allow recovery'
    $script:DockerOperationLock = $null
}
Run-Test 'corrupt reboot journal fails closed' {
    $script:DockerOperationLock = [pscustomobject]@{}
    function Test-CurrentProcessElevated { $true }
    function Invoke-ProcessWithTimeout { throw 'Unexpected reboot' }
    Set-Content -LiteralPath $DockerHostRebootPath -Value '{}'
    Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Corrupt journal ignored'
    $script:DockerOperationLock = $null
}
Run-Test 'reboot requires operation lock' {
    $script:DockerOperationLock = $null
    function Invoke-ProcessWithTimeout { throw 'Unexpected reboot' }
    Assert-True (-not (Request-DockerHostRecoveryReboot -Reason test)) 'Reboot without lock'
}
Run-Test 'service inventory survives retries and clears only after completed recovery' {
    Save-DockerRecoveryInventory -ServiceNames @('homepage','plex')
    Save-DockerRecoveryInventory -ServiceNames @('plex')
    Assert-True ((@(Get-DockerRecoveryInventory) -join ',') -eq 'homepage,plex') 'Original inventory overwritten'
    function Restart-DockerDesktopClean { throw 'Restarted an already healthy engine' }
    function Start-CriticalDockerServices { $true }
    function Repair-WslComposeBindServices { param($ServiceNames) Assert-True (($ServiceNames -join ',') -eq 'homepage,plex') 'Lost saved inventory'; $false }
    Assert-True (-not (Restart-DockerDesktop -ResumeOnly)) 'Failed bind repair accepted'
    Assert-True (Test-Path -LiteralPath $DockerRecoveryInventoryPath) 'Failed recovery lost inventory'
    function Repair-WslComposeBindServices { $true }
    function Repair-WindowsComposeServices { $true }
    function Test-DockerContainerReady { $true }
    function Get-ConfirmedDockerHealth { Health }
    Assert-True (Restart-DockerDesktop -ResumeOnly) 'Resume failed'
    Assert-True (-not (Test-Path -LiteralPath $DockerRecoveryInventoryPath)) 'Completed recovery remained pending'
}
Run-Test 'pending recovery resumes without engine restart and respects repair cooldown' {
    Save-DockerRecoveryInventory -ServiceNames @('homepage')
    function Write-Log { param($message) Add-Content -LiteralPath $logFilePath -Value "$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) - $message" }
    function Test-DockerDaemon { $true }
    function Restart-DockerDesktop { param([switch]$ResumeOnly) Assert-True $ResumeOnly 'Restarted instead of resuming'; $script:calls++; $false }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Failed resume reported healthy'
    Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Cooldown reported healthy'
    Assert-True ($script:calls -eq 1) 'Repeated recovery bypassed cooldown'
}
Run-Test 'failed daemon readiness reaches hard recovery' {
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=0;Output=''} }
    function Wait-DockerDesktopReady { $false }
    function Invoke-DockerDesktopHardRecovery { $script:events += 'hard-recovery'; $true }
    Assert-True (Restart-DockerDesktopClean) 'Hard recovery failed'
    Assert-True (($script:events -join ',') -eq 'hard-recovery') 'Hard recovery was skipped'
}
Run-Test 'CLI error with a ready daemon does not restart again' {
    function Invoke-DockerCliWithTimeout { param($Arguments) $script:events += ($Arguments -join ' '); [pscustomobject]@{ExitCode=124;Output='timeout'} }
    function Wait-DockerDesktopReady { $true }
    Assert-True (Restart-DockerDesktopClean) 'Readiness not honored'
    Assert-True ($script:events.Count -eq 1) 'Ready daemon was stopped again'
}
Run-Test 'shared lock rejects another process and releases cleanly' {
    Assert-True (Enter-DockerOperationLock) 'Could not acquire test lock'
    try {
        $command = ". '$suiteRoot\docker-desktop-common.ps1' -ProjectRoot '$ProjectRoot'; `$DockerOperationLockPath='$DockerOperationLockPath'; `$DockerLogFilePath='$scratch\child.log'; if (Enter-DockerOperationLock) { Exit-DockerOperationLock; exit 9 }; exit 0"
        $r = Invoke-ProcessWithTimeout -FilePath powershell.exe -Arguments @('-NoProfile','-Command',$command) -Quiet
        Assert-True ($r.ExitCode -eq 0) 'Concurrent process acquired lock'
    } finally { Exit-DockerOperationLock }
    Assert-True (Enter-DockerOperationLock) 'Released lock cannot be reacquired'
    Exit-DockerOperationLock
}

Run-Test 'working WSL shell with missing Docker socket is integration failure' {
    function Test-DockerDaemon { $true }
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output=''} }
    function Test-WslDockerIntegration { $false }
    function Test-CriticalDockerReadiness { throw 'Integration must be checked before containers' }
    Assert-True ((Get-DockerHealthSnapshot).Kind -eq 'WslIntegration') 'Misclassified as an application failure'
}
Run-Test 'confirmed integration failure uses full recovery' {
    function Get-ConfirmedDockerHealth { Health WslIntegration }
    function Get-DockerHealthSnapshot { Health WslIntegration }
    function Test-DockerRestartAllowed { $true }
    function Restart-DockerDesktop { $script:events += 'restart'; $true }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 0) 'Integration recovery failed'
    Assert-True (($script:events -join ',') -eq 'alert,restart,alert') 'Wrong recovery path'
}
Run-Test 'integration failure respects restart cooldown' {
    function Get-ConfirmedDockerHealth { Health WslIntegration }
    function Test-DockerRestartAllowed { $false }
    function Restart-DockerDesktop { throw 'Restart during cooldown' }
    Assert-True ((Invoke-DockerHealthMonitor) -eq 1) 'Cooldown not respected'
    Assert-True ($script:events.Count -eq 0) 'Cooldown caused mutations'
}
Run-Test 'integration probe rejects zero-exit missing-integration stub' {
    Set-Item Function:Test-WslDockerIntegration $realIntegrationProbe
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=0;Output='Enable WSL integration in Docker Desktop settings.'} }
    Assert-True (-not (Test-WslDockerIntegration)) 'Stub accepted as functional Docker'
}
Run-Test 'integration probe requires server version and successful exit' {
    Set-Item Function:Test-WslDockerIntegration $realIntegrationProbe
    function Invoke-WslCommand {
        param($Command,$TimeoutSeconds,$MaxAttempts,[switch]$Quiet)
        Assert-True ($Command -match '/usr/bin/docker info' -and $Command -match 'test -S /var/run/docker.sock') 'Wrong client probe'
        Assert-True ($TimeoutSeconds -eq 20 -and $MaxAttempts -eq 1) 'Unbounded integration probe'
        [pscustomobject]@{ExitCode=0;Output='WSL_DOCKER_READY=29.5.0'}
    }
    Assert-True (Test-WslDockerIntegration) 'Valid server rejected'
    function Invoke-WslCommand { [pscustomobject]@{ExitCode=1;Output='WSL_DOCKER_READY=29.5.0'} }
    Assert-True (-not (Test-WslDockerIntegration)) 'Failed command accepted'
}
Run-Test 'integration wait permits delayed readiness' {
    Set-Item Function:Wait-WslDockerIntegration $realIntegrationWait
    function Test-WslDockerIntegration { $script:calls++; $script:calls -ge 3 }
    Assert-True (Wait-WslDockerIntegration -TimeoutSeconds 5 -IntervalSeconds 0) 'Delayed readiness failed'
    Assert-True ($script:calls -eq 3) 'Readiness retries incorrect'
}
Run-Test 'integration wait returns failure at deadline' {
    Set-Item Function:Wait-WslDockerIntegration $realIntegrationWait
    function Test-WslDockerIntegration { $false }
    Assert-True (-not (Wait-WslDockerIntegration -TimeoutSeconds 0)) 'Failure incorrectly ready'
}
Run-Test 'critical startup never mutates services without WSL integration' {
    function Test-DockerDaemon { $true }
    function Wait-WslDockerIntegration { $false }
    function Start-DockerContainerIfPresent { throw 'Started before integration ready' }
    function Test-RequiredDockerNetwork { throw 'Proceeded before integration ready' }
    Assert-True (-not (Start-CriticalDockerServices)) 'Startup falsely successful'
}
Run-Test 'Desktop readiness requires both Windows and WSL engines' {
    function Wait-DockerDaemon { $true }
    function Wait-WslDockerIntegration { $false }
    Assert-True (-not (Wait-DockerDesktopReady)) 'Windows-only readiness accepted'
}
Run-Test 'restart escalates missing integration despite healthy Windows engine' {
    function Invoke-DockerCliWithTimeout { [pscustomobject]@{ExitCode=0;Output=''} }
    function Wait-DockerDaemon { $true }
    function Wait-WslDockerIntegration { $false }
    function Invoke-DockerDesktopHardRecovery { $script:events += 'hard-recovery'; $false }
    Assert-True (-not (Restart-DockerDesktopClean)) 'Missing integration reported recovered'
    Assert-True (($script:events -join ',') -eq 'hard-recovery') 'No bounded escalation'
}

. (Join-Path $suiteRoot 'test-recovery-policy.cases.ps1')

if ($LiveReadOnly) {
    Run-Test 'live native WSL Docker integration is functional' {
        Set-Item Function:Test-WslDockerIntegration $realIntegrationProbe
        Assert-True (Test-WslDockerIntegration) 'Live native WSL Docker unavailable'
    }
    Run-Test 'real WSL argv preserves shell quoting and arrays' {
        $r = Invoke-WslCommand -Command 'values=("hello world" "quote\"inside" "trailing\\"); printf "%s\n" "${values[@]}"' -MaxAttempts 1 -Quiet
        Assert-True ($r.ExitCode -eq 0 -and $r.Output -eq "hello world`nquote`"inside`ntrailing\") ($r | ConvertTo-Json -Compress)
    }
    Run-Test 'real Windows Docker inspection preserves Go template spaces' {
        $r = Invoke-DockerCli -Arguments @('inspect','--format','{{.Name}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}','plex') -Quiet
        Assert-True ($r.ExitCode -eq 0 -and $r.Output -eq '/plex|none') ($r | ConvertTo-Json -Compress)
    }
    Run-Test 'real installed Bash sentinel passes' {
        $r = Invoke-WslCommand -Command 'bash /mnt/e/Scripts/docker-stateful-sentinel-check.sh' -TimeoutSeconds 90 -MaxAttempts 1 -Quiet
        Assert-True ($r.ExitCode -eq 0) ($r | ConvertTo-Json -Compress)
    }
}
Write-Host "RESULT passed=$script:passed failed=$script:failed"
if ($script:failed -gt 0) { exit 1 }
