# Run elevated after the reviewed change reaches main. Only Telegraf restarts.
[CmdletBinding()]
param([string]$Config = 'C:\Program Files\InfluxData\telegraf\telegraf.conf')

$ErrorActionPreference = 'Stop'

function Update-MemoryConfig {
    param([string]$Original, [string]$Block)
    $begin = '# BEGIN host memory telemetry'
    $end = '# END host memory telemetry'
    $begins = [regex]::Matches($Original, '(?m)^' + [regex]::Escape($begin) + '\r?$').Count
    $ends = [regex]::Matches($Original, '(?m)^' + [regex]::Escape($end) + '\r?$').Count
    $managed = $begin + "`r`n" + $Block.TrimEnd() + "`r`n" + $end
    if ($begins -eq 0 -and $ends -eq 0) { return $Original.TrimEnd() + "`r`n`r`n" + $managed + "`r`n" }
    $pattern = '(?ms)^' + [regex]::Escape($begin) + '\r?$.*?^' + [regex]::Escape($end) + '(?=\r?$)'
    if ($begins -ne 1 -or $ends -ne 1 -or [regex]::Matches($Original, $pattern).Count -ne 1) {
        throw 'Ambiguous host memory configuration markers; leaving configuration unchanged'
    }
    return [regex]::Replace($Original, $pattern, [Text.RegularExpressions.MatchEvaluator]{ param($match) $managed })
}

# Create empty first, apply the existing config ACL, then write any credentials.
function Save-ProtectedConfig {
    param([string]$Path, [byte[]]$Bytes, $Acl)
    $file = [IO.File]::Open($Path, [IO.FileMode]::CreateNew)
    $file.Dispose()
    Set-Acl -LiteralPath $Path -AclObject $Acl
    [IO.File]::WriteAllBytes($Path, $Bytes)
}

if ($MyInvocation.InvocationName -eq '.') { return }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this installer elevated' }
if ((Get-Service telegraf).Status -ne 'Running') { throw 'Telegraf must already be running; do not install during a held maintenance stop' }

$directory = Split-Path $Config
$probe = Join-Path $directory 'collect-wsl-memory.ps1'
$source = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'collect-wsl-memory.ps1'))
$originalBytes = [IO.File]::ReadAllBytes($Config)
$original = [IO.File]::ReadAllText($Config)
$existed = Test-Path -LiteralPath $probe
$oldProbe = if ($existed) { [IO.File]::ReadAllBytes($probe) } else { $null }
$block = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'telegraf.conf')).Replace('C:\Program Files\InfluxData\telegraf\collect-wsl-memory.ps1', $probe)
$updated = Update-MemoryConfig -Original $original -Block $block
$encoding = [Text.UTF8Encoding]::new($false)
if ($updated -ceq $original -and $existed -and [Convert]::ToBase64String($source) -ceq [Convert]::ToBase64String($oldProbe)) {
    Write-Output 'Host memory telemetry is already installed.'
    exit 0
}

$suffix = [Guid]::NewGuid().ToString('N')
$candidate = Join-Path $directory "host-memory-candidate-$suffix.conf"
$candidateProbe = Join-Path $directory "host-memory-candidate-$suffix.ps1"
$acl = Get-Acl -LiteralPath $Config
try {
    [IO.File]::WriteAllBytes($candidateProbe, $source)
    Save-ProtectedConfig -Path $candidate -Bytes $encoding.GetBytes($updated.Replace($probe, $candidateProbe)) -Acl $acl
    # Read-only collection: --test never writes to configured outputs. Do not
    # print the existing configuration, credentials or the captured test output.
    $ErrorActionPreference = 'Continue'
    try {
        $testOutput = & (Join-Path $directory 'telegraf.exe') --config $candidate --input-filter 'win_perf_counters:exec:http_response' --test 2>&1 | Out-String
        $testExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
    if ($testExit -ne 0 -or $testOutput -notmatch 'wsl_memory,[^\r\n]*collect_up=1i' -or $testOutput -notmatch 'System_Cache_Resident_Bytes=' -or $testOutput -notmatch 'wsl_process,[^\r\n]*Working_Set=') {
        throw 'Memory telemetry validation failed; installed configuration was not changed'
    }
} finally {
    Remove-Item -LiteralPath $candidate, $candidateProbe -ErrorAction SilentlyContinue
}

if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Config)) -cne [Convert]::ToBase64String($originalBytes)) {
    throw 'Telegraf configuration changed during validation; leaving it unchanged'
}
if ((Test-Path -LiteralPath $probe) -ne $existed -or ($existed -and [Convert]::ToBase64String([IO.File]::ReadAllBytes($probe)) -cne [Convert]::ToBase64String($oldProbe))) {
    throw 'Installed memory reader changed during validation; leaving it unchanged'
}
$backup = $Config + '.host-memory-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $suffix
Save-ProtectedConfig -Path $backup -Bytes $originalBytes -Acl $acl
if ($existed) { [IO.File]::WriteAllBytes($backup + '.probe.ps1', $oldProbe) }
try {
    [IO.File]::WriteAllBytes($probe, $source)
    [IO.File]::WriteAllText($Config, $updated, $encoding)
    Restart-Service telegraf
    (Get-Service telegraf).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    Write-Output "Host memory telemetry installed. Original configuration: $backup"
} catch {
    [IO.File]::WriteAllBytes($Config, $originalBytes)
    if ($existed) { [IO.File]::WriteAllBytes($probe, $oldProbe) }
    else { Remove-Item -LiteralPath $probe -ErrorAction SilentlyContinue }
    Restart-Service telegraf
    throw
}
