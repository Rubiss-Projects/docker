$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'install.ps1')

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$original = "# Existing input`r`n[[outputs.influxdb_v2]]`r`ntoken = 'test-only-placeholder'`r`n"
$block = "[[inputs.win_perf_counters]]`ninterval = '10s'"
$installed = Update-MemoryConfig $original $block
Assert-True ($installed.StartsWith($original)) 'Existing configuration changed'
Assert-True ((Update-MemoryConfig $installed $block) -ceq $installed) 'Install is not idempotent'
$next = Update-MemoryConfig $installed 'replacement = true'
Assert-True ($next.Contains('replacement = true') -and -not $next.Contains("interval = '10s'")) 'Managed block was not replaced'
Assert-True ($next.StartsWith($original)) 'Replacement changed unrelated configuration'

foreach ($text in @(
    "# BEGIN host memory telemetry`nmissing end",
    "# END host memory telemetry`nmissing beginning",
    "# END host memory telemetry`n# BEGIN host memory telemetry",
    ($installed + $installed)
)) {
    $refused = $false
    try { $null = Update-MemoryConfig $text $block } catch { $refused = $true }
    Assert-True $refused 'Ambiguous configuration markers accepted'
}
Write-Output 'Installer: preserve unrelated settings, idempotent replacement and four marker refusals passed.'
