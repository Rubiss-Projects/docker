# Dot-sourced by capture.ps1 while its global diagnostic mutex is held.
# This reserved PLA collector is separate from WPR and other diagnostic sessions.
$ioCollector = 'TransmissionStallIO-v1'
$logman = Join-Path $env:windir 'System32\logman.exe'

function Invoke-TraceCommand([string]$Arguments) {
    Invoke-DiagnosticCommand $logman $Arguments '' 5
}

function Start-WindowsIoTrace([string]$Directory, [string]$CaptureId) {
    # Recover our own prior definition after an interrupted capture. Never stop
    # a global kernel logger or any other tool's session.
    try { [void](Invoke-TraceCommand "stop $ioCollector") } catch { }
    try { [void](Invoke-TraceCommand "delete $ioCollector") } catch { }
    # Keep at most five 64 MiB traces including the new one, independently of JSON.
    Get-ChildItem $Directory -Filter 'io-*.etl' | Where-Object Name -Match '^io-\d{8}T\d{9}Z_\d+\.etl$' |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -Skip 4 | Remove-Item
    $base = Join-Path $Directory ('io-' + $CaptureId + '.etl')
    $providers = Join-Path $PSScriptRoot 'io-providers.txt'
    # A managed collector (no -ets) is essential: PLA owns the duration timer,
    # so a killed PowerShell process cannot leave tracing running indefinitely.
    [void](Invoke-TraceCommand "create trace $ioCollector -o `"$base`" -f bincirc -max 64 -bs 64 -nb 16 64 -rf 00:00:20 -pf `"$providers`"")
    $started = [DateTime]::UtcNow
    [void](Invoke-TraceCommand "start $ioCollector")
    return @{
        status = 'running'; startedAt = $started.ToString('o'); durationSeconds = 20
        outputBase = $base; maxFileMiB = 64
        qpcFrequency = [Diagnostics.Stopwatch]::Frequency
        processes = @(Get-Process | Select-Object Id,ProcessName)
    }
}

function Complete-WindowsIoTrace([hashtable]$Trace) {
    if ($Trace.status -ne 'running') { return }
    try {
        $remaining = 21 - ([DateTime]::UtcNow - [DateTime]::Parse($Trace.startedAt).ToUniversalTime()).TotalSeconds
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([int]($remaining * 1000)) }
        # Query PLA without parsing localized logman output. Verify its timer
        # stopped collection; explicitly stop if completion is slightly delayed.
        $collector = New-Object -ComObject Pla.DataCollectorSet
        try {
            $collector.Query($ioCollector, $null)
            if ($collector.Status -ne 0) { [void](Invoke-TraceCommand "stop $ioCollector") }
            $Trace.buffersLost = @($collector.DataCollectors | ForEach-Object { $_.BuffersLost })
        } finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($collector) }
        $stem = [IO.Path]::GetFileNameWithoutExtension($Trace.outputBase)
        $Trace.files = @(Get-ChildItem ([IO.Path]::GetDirectoryName($Trace.outputBase)) -Filter "$stem*.etl" | Select-Object FullName,Length)
        if ($Trace.files.Count -eq 0 -or @($Trace.files | Where-Object Length -LE 0).Count) { throw 'No Windows trace file was written' }
        $Trace.status = 'complete'
    } catch {
        $Trace.status = 'failed'
        $Trace.error = $_.Exception.Message
    } finally { $Trace.finishedAt = [DateTime]::UtcNow.ToString('o') }
}
