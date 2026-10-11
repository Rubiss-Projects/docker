# Run elevated from the reviewed checkout. Installs scripts without restarting Docker.
[CmdletBinding()]
param ([string]$Destination = 'E:\Scripts')
$ErrorActionPreference = 'Stop'

function Get-LegacyWatchdogWebhook {
    param ([string]$Path)
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'Cannot parse the installed watchdog.' }
    $assignments = @($ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left -is [Management.Automation.Language.VariableExpressionAst] -and
        $node.Left.VariablePath.UserPath -eq 'discordWebhookUrl'
    }, $false))
    if ($assignments.Count -ne 1) { throw 'Cannot safely migrate the existing notification setting.' }
    $expression = $assignments[0].Right.Expression
    if ($expression -isnot [Management.Automation.Language.StringConstantExpressionAst]) {
        throw 'Existing notification setting is not a literal; refusing to evaluate it.'
    }
    return $expression.Value
}

function Assert-WatchdogFilesUnchanged {
    param ([string]$Directory, $Expected)
    foreach ($name in $Expected.Keys) {
        $path = Join-Path $Directory $name
        $actual = if (Test-Path -LiteralPath $path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }
        if ($actual -ne $Expected[$name]) { throw "Installed file changed: $name. Review it before deployment." }
    }
}

function Write-ProtectedWatchdogJson {
    param ([string]$Path, $Value, $Acl)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew)
    $stream.Dispose()
    Set-Acl -LiteralPath $Path -AclObject $Acl
    $Value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-WatchdogContainerSnapshot {
    $query = Invoke-DockerCli -Arguments @('ps', '-q') -Quiet
    if ($query.ExitCode -ne 0) { throw 'Cannot capture running container identities.' }
    $ids = @($query.Output -split '\s+' | Where-Object { $_ })
    if ($ids.Count -eq 0) { throw 'No running containers; defer this live installation until recovery finishes.' }
    $query = Invoke-DockerCli -Arguments (@('inspect', '--format', '{{.Name}}|{{.Id}}|{{.State.StartedAt}}') + $ids) -Quiet
    if ($query.ExitCode -ne 0) { throw 'Cannot capture container start times.' }
    return (($query.Output -split "`n" | Sort-Object) -join "`n").Trim()
}

if ($MyInvocation.InvocationName -eq '.') { return }
$Destination = [IO.Path]::GetFullPath($Destination)
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this installer elevated.' }
$files = @('docker-desktop-common.ps1', 'start-docker-desktop.ps1', 'docker-desktop-nightly-maintenance.ps1', 'recovery-policy.ps1')
$manifestPath = Join-Path $Destination 'docker-watchdog-installation.json'
$notificationPath = Join-Path $Destination 'docker-watchdog-notifications.json'
$expected = @{
    'docker-desktop-common.ps1' = '4657AE19D918CDA87734BFA9A1F8F5D31C13D02C5F93C5604DEB97040D32B6C4'
    'start-docker-desktop.ps1' = '2FCBF3C1E50E4633753AC5FB89A919A4242B80C72A3C8724EEE7ABECDC85E924'
    'docker-desktop-nightly-maintenance.ps1' = '30A050F3CA1FA96810DF257061335BEFA93B2830271043DBEEEBCFF0A75F880E'
    'recovery-policy.ps1' = $null
}
if (Test-Path -LiteralPath $manifestPath) {
    $installed = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($name in $files) {
        $hash = $installed.Hashes.$name
        if ($hash -notmatch '^[0-9A-Fa-f]{64}$') { throw 'Invalid watchdog installation manifest.' }
        $expected[$name] = $hash
    }
}
Assert-WatchdogFilesUnchanged -Directory $Destination -Expected $expected
foreach ($name in $files) {
    $tokens = $null; $errors = $null
    [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count) { throw "Candidate syntax error in $name" }
}
$watchdogName = 'Start Docker Desktop if not running'
$nightlyName = 'Docker Desktop Nightly Restart'
$tasks = @(Get-ScheduledTask -TaskName $watchdogName, $nightlyName)
if ($tasks.Count -ne 2 -or -not ($tasks | Where-Object TaskName -eq $watchdogName).Settings.Enabled) {
    throw 'Expected an enabled watchdog and the existing nightly task. Do not override an intentional maintenance stop.'
}
$backup = Join-Path $Destination ('backups\watchdog-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$taskStates = @{}
foreach ($task in $tasks) {
    $taskStates[$task.TaskName] = $task.Settings.Enabled
    Export-ScheduledTask -TaskName $task.TaskName | Set-Content -LiteralPath (Join-Path $backup ($task.TaskName + '.xml'))
}
$taskStates | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'task-states.json')
. (Join-Path $Destination 'docker-desktop-common.ps1')
$locked = $false; $copied = $false; $success = $false; $createdNotifications = $false
$manifestExisted = Test-Path -LiteralPath $manifestPath
try {
    foreach ($task in $tasks) { Disable-ScheduledTask -TaskName $task.TaskName | Out-Null }
    $deadline = (Get-Date).AddMinutes(30)
    while (@(Get-ScheduledTask -TaskName $watchdogName, $nightlyName | Where-Object State -eq Running).Count) {
        if ((Get-Date) -ge $deadline) { throw 'Active recovery has not finished; leaving it untouched.' }
        Start-Sleep -Seconds 5
    }
    $locked = Enter-DockerOperationLock -WaitSeconds 30
    if (-not $locked) { throw 'Another maintenance operation owns the lock.' }
    Assert-WatchdogFilesUnchanged -Directory $Destination -Expected $expected
    $before = Get-WatchdogContainerSnapshot
    foreach ($name in $files) {
        if (Test-Path -LiteralPath (Join-Path $Destination $name)) {
            Copy-Item -LiteralPath (Join-Path $Destination $name) -Destination (Join-Path $backup $name)
        }
    }
    if ($manifestExisted) { Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $backup 'docker-watchdog-installation.json') }
    if (-not (Test-Path -LiteralPath $notificationPath)) {
        $url = Get-LegacyWatchdogWebhook -Path (Join-Path $Destination 'start-docker-desktop.ps1')
        $createdNotifications = $true
        Write-ProtectedWatchdogJson -Path $notificationPath -Value @{DiscordWebhookUrl=$url} -Acl (Get-Acl (Join-Path $Destination 'start-docker-desktop.ps1'))
    }
    $copied = $true
    foreach ($name in $files) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $Destination $name) -Force }
    foreach ($entry in @('start-docker-desktop.ps1', 'docker-desktop-nightly-maintenance.ps1')) {
        $validation = Invoke-ProcessWithTimeout -FilePath 'powershell.exe' -Arguments @('-NoProfile', '-File', (Join-Path $Destination $entry), '-ValidateOnly') -TimeoutSeconds 300 -Quiet
        if ($validation.ExitCode -ne 0) { throw "Read-only validation failed for $entry; rolling back." }
    }
    if ((Get-WatchdogContainerSnapshot) -cne $before) { throw 'Containers changed during installation; investigate before accepting deployment.' }
    $hashes = @{}
    foreach ($name in $files) { $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $Destination $name)).Hash }
    @{InstalledAt=(Get-Date -Format o);Hashes=$hashes} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath
    $success = $true
    Write-Host "Watchdog installed without changing container identities or start times. Backup: $backup"
    Write-Host 'Minute watchdog remains enabled; unconditional nightly restart task is disabled.'
} catch {
    if ($copied) {
        foreach ($name in $files) {
            $saved = Join-Path $backup $name
            if (Test-Path -LiteralPath $saved) { Copy-Item -LiteralPath $saved -Destination (Join-Path $Destination $name) -Force }
            elseif ($null -eq $expected[$name]) { Remove-Item -LiteralPath (Join-Path $Destination $name) -ErrorAction SilentlyContinue }
        }
        if ($manifestExisted) { Copy-Item -LiteralPath (Join-Path $backup 'docker-watchdog-installation.json') -Destination $manifestPath -Force }
        else { Remove-Item -LiteralPath $manifestPath -ErrorAction SilentlyContinue }
    }
    if ($createdNotifications) { Remove-Item -LiteralPath $notificationPath -ErrorAction SilentlyContinue }
    throw
} finally {
    if ($locked) { Exit-DockerOperationLock }
    foreach ($task in $tasks) {
        if ($success -and $task.TaskName -eq $nightlyName) { continue }
        if ($taskStates[$task.TaskName]) { Enable-ScheduledTask -TaskName $task.TaskName | Out-Null }
    }
}
