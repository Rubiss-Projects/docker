$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'install.ps1')
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('watchdog-installer-tests-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
$fixture = Join-Path $scratch 'start.ps1'
$sentinel = Join-Path $scratch 'must-not-run'
Set-Content -LiteralPath $fixture -Value ('$discordWebhookUrl = ''test-value''; Set-Content -LiteralPath ''' + $sentinel + ''' -Value bad')
if ((Get-LegacyWatchdogWebhook -Path $fixture) -cne 'test-value' -or (Test-Path -LiteralPath $sentinel)) {
    throw 'Literal migration either changed the setting or executed the original script.'
}
Write-Host 'PASS notification migration does not evaluate the old script'
Set-Content -LiteralPath $fixture -Value '$discordWebhookUrl = (Get-Content secret.txt)'
$rejected = $false
try { Get-LegacyWatchdogWebhook -Path $fixture | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'Accepted a computed notification setting.' }
Write-Host 'PASS computed notification settings are rejected'
$expected = @{'start.ps1'=(Get-FileHash -LiteralPath $fixture).Hash; 'new.ps1'=$null}
Assert-WatchdogFilesUnchanged -Directory $scratch -Expected $expected
Add-Content -LiteralPath $fixture -Value '# concurrent change'
$rejected = $false
try { Assert-WatchdogFilesUnchanged -Directory $scratch -Expected $expected } catch { $rejected = $true }
if (-not $rejected) { throw 'Accepted a concurrently edited watchdog.' }
Write-Host 'PASS installation detects concurrent edits'
$expected['start.ps1'] = (Get-FileHash -LiteralPath $fixture).Hash
Set-Content -LiteralPath (Join-Path $scratch 'new.ps1') -Value '# unexpected file'
$rejected = $false
try { Assert-WatchdogFilesUnchanged -Directory $scratch -Expected $expected } catch { $rejected = $true }
if (-not $rejected) { throw 'Overwrote an unrecognized new helper.' }
Write-Host 'PASS installation refuses unexpected helper files'
$script:started = '2026-10-11T12:00:00Z'
function Invoke-DockerCli {
    param($Arguments, [switch]$Quiet)
    if ($Arguments[0] -eq 'ps') { return [pscustomobject]@{ExitCode=0;Output='abc'} }
    [pscustomobject]@{ExitCode=0;Output=('channels-dvr|abc|' + $script:started)}
}
$before = Get-WatchdogContainerSnapshot
$script:started = '2026-10-11T12:05:00Z'
if ((Get-WatchdogContainerSnapshot) -ceq $before) { throw 'Snapshot ignored a restart with the same container ID.' }
Write-Host 'PASS installation verification detects restarts without recreation'
$guard = Enter-WatchdogInstallationLock -Directory $scratch
try {
    $rejected = $false
    try { $other = Enter-WatchdogInstallationLock -Directory $scratch; $other.Dispose() } catch { $rejected = $true }
    if (-not $rejected) { throw 'Concurrent installer acquired task-state ownership.' }
} finally { $guard.Dispose() }
$guard = Enter-WatchdogInstallationLock -Directory $scratch
$guard.Dispose()
Write-Host 'PASS installer lock rejects concurrent task-state ownership and releases cleanly'
$manifestFixture = Join-Path $scratch 'installation.json'
Write-WatchdogInstallationManifest -Path $manifestFixture -Value @{Hashes=@{common='first'}}
Write-WatchdogInstallationManifest -Path $manifestFixture -Value @{Hashes=@{common='second'}}
$savedManifest = Get-Content -LiteralPath $manifestFixture -Raw
if (($savedManifest | ConvertFrom-Json).Hashes.common -ne 'second') { throw 'Manifest replacement did not preserve valid JSON.' }
$rejected = $false
try {
    & {
        function Set-Content { param($LiteralPath) [IO.File]::WriteAllText($LiteralPath, '{partial'); throw 'interrupted manifest write' }
        Write-WatchdogInstallationManifest -Path $manifestFixture -Value @{Hashes=@{common='third'}}
    }
} catch { $rejected = $true }
if (-not $rejected -or (Get-Content -LiteralPath $manifestFixture -Raw) -cne $savedManifest) { throw 'Interrupted manifest write damaged installed state.' }
Write-Host 'PASS interrupted manifest write retains the last complete installation state'
