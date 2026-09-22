# Run elevated after deploying the repository. Preserve the existing Telegraf
# inputs, output and credentials; replace only our marked configuration block.
[CmdletBinding()]
param([string]$Config = 'C:\Program Files\InfluxData\telegraf\telegraf.conf')
$ErrorActionPreference = 'Stop'
$begin = '# BEGIN transmission observability (managed by E:\Docker\transmission)'
$end = '# END transmission observability'
$original = [IO.File]::ReadAllText($Config)
$block = $begin + "`r`n" + [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'telegraf.conf')) + "`r`n" + $end
$pattern = '(?s)' + [regex]::Escape($begin) + '.*?' + [regex]::Escape($end)
$updated = if ($original.Contains($begin)) { [regex]::Replace($original, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $block }) } else { $original.TrimEnd() + "`r`n`r`n" + $block + "`r`n" }
if ($updated -eq $original) { Write-Output 'Transmission Telegraf configuration is already installed.'; exit 0 }
$backup = $Config + '.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
Copy-Item -LiteralPath $Config -Destination $backup
try {
    [IO.File]::WriteAllText($Config, $updated, [Text.UTF8Encoding]::new($false))
    # --test does not write to InfluxDB and validates the actual Windows inputs.
    # Windows PowerShell 5 treats informational native stderr as ErrorRecords.
    $ErrorActionPreference = 'Continue'
    try {
        & (Join-Path (Split-Path $Config) 'telegraf.exe') --config $Config --input-filter 'exec:http_response:win_perf_counters' --test 2>&1 | Out-String | Write-Verbose
        $validationExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
    if ($validationExit -ne 0) { throw 'Telegraf validation failed' }
    Restart-Service telegraf
    (Get-Service telegraf).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    Write-Output 'Transmission metrics and storage latency collection installed.'
} catch {
    Copy-Item -LiteralPath $backup -Destination $Config -Force
    Restart-Service telegraf
    throw
}
