param([switch]$Install, [switch]$CaptureNow, [switch]$EnableLinuxTracing)
$ErrorActionPreference = 'Stop'
if ($EnableLinuxTracing -and (-not $CaptureNow -or $Install)) { throw 'Linux tracing requires an explicit manual -CaptureNow run, not installation or automatic capture.' }
$taskName = 'Transmission stall diagnostics'
$outputDir = 'E:\Scripts\Logs\transmission-stalls'
$helper = 'transmission-stall-snapshot'
$docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'

if ($Install) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath)
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId 'Rubiss' -LogonType S4U -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Bounded Linux proc and Windows I/O stall evidence; no service recovery or torrent mutations.' -Force | Out-Null
    exit 0
}

# Bound Docker CLI waits independently of the daemon and snapshot alarm.
function Invoke-DiagnosticCommand([string]$Executable, [string]$Arguments, [string]$InputText = '', [int]$Seconds = 15) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = $Arguments
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if ($InputText) { $process.StandardInput.WriteLine($InputText) }
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($Seconds * 1000)) {
            $process.Kill()
            throw "Diagnostic command timed out: $Executable"
        }
        if ($process.ExitCode -ne 0) { throw ('Diagnostic command failed: ' + $stdout.Result + $stderr.Result) }
        return $stdout.Result
    } finally { $process.Dispose() }
}

function Invoke-DockerBounded([string]$Arguments, [string]$InputText = '', [int]$Seconds = 15) {
    Invoke-DiagnosticCommand $docker $Arguments $InputText $Seconds
}

. (Join-Path $PSScriptRoot 'windows-trace.ps1')
. (Join-Path $PSScriptRoot 'clock-calibration.ps1')

$mutex = New-Object System.Threading.Mutex($false, 'Global\TransmissionStallDiagnostics')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] {
        # WaitOne grants ownership before throwing when the prior holder died.
        $locked = $true
    }
    if (-not $locked) { exit 0 }
    $state = (Invoke-DockerBounded 'inspect --format "{{json .State}}" transmission') | ConvertFrom-Json
    if (-not $state.Running) { exit 0 }
    $last = @($state.Health.Log) | Select-Object -Last 1
    if (-not $CaptureNow -and (-not $last -or $last.ExitCode -eq 0)) { exit 0 }
    [void](New-Item -ItemType Directory -Path $outputDir -Force)
    $latest = Get-ChildItem $outputDir -Filter 'capture-*.json' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    # Capture at most once per five minutes, not once per repeated failed probe.
    if (-not $CaptureNow -and $latest -and $latest.LastWriteTimeUtc -gt [DateTime]::UtcNow.AddMinutes(-5)) { exit 0 }
    $image = (Invoke-DockerBounded 'inspect --format "{{.Image}}" transmission').Trim()
    $helperIdentity = Join-Path $outputDir 'linux-helper-image.txt'
    if ($EnableLinuxTracing -and (Test-Path -LiteralPath $helperIdentity)) { $image = (Get-Content -LiteralPath $helperIdentity -Raw).Trim() }
    if ($image -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Unexpected image identity' }
    $source = Get-Content (Join-Path $PSScriptRoot 'snapshot.py') -Raw
    $captureId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $windowsTrace = @{ status = 'not_started' }
    # Local immutable diagnostic image; no pulls, host mounts or networking.
    # Automatic collection reads proc only. Attachment requires manual opt-in.
    $traceEnabled = if ($EnableLinuxTracing) { '1' } else { '0' }
    $clockBefore = Get-ClockCalibration
    try {
        # Tracing failures must not suppress the existing Linux evidence.
        try { $windowsTrace = Start-WindowsIoTrace $outputDir $captureId }
        catch { $windowsTrace = @{ status = 'failed'; error = $_.Exception.Message } }
        $raw = Invoke-DockerBounded "run --rm -i --name $helper --label diagnostic.owner=transmission-stall-capture --pull never --network none --pid container:transmission --read-only --cap-drop ALL --cap-add SYS_PTRACE --cap-add DAC_READ_SEARCH --security-opt no-new-privileges --memory 128m --memory-swap 128m --pids-limit 16 --env TRANSMISSION_TRACE_ENABLED=$traceEnabled --user 0 --entrypoint python3 $image -" $source 25
        if ($raw.Length -gt 1048576) { throw 'Snapshot exceeded 1 MiB bound' }
        $evidence = $raw | ConvertFrom-Json
        Complete-WindowsIoTrace $windowsTrace
        $clockAfter = Get-ClockCalibration
        $report = @{ capturedAt = [DateTime]::UtcNow.ToString('o'); manualTest = [bool]$CaptureNow; state = $state; evidence = $evidence; windowsTrace = $windowsTrace; helperImage = $image; clockCalibration = (Compare-ClockCalibration $clockBefore $clockAfter) }
        $destination = Join-Path $outputDir ('capture-' + $captureId + '.json')
        $report | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $destination -Encoding UTF8
        # Only our own diagnostic reports are rotated, never media or backups.
        Get-ChildItem $outputDir -Filter 'capture-*.json' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -Skip 20 | Remove-Item
        Write-Output $destination
        if ($windowsTrace.status -ne 'complete') { throw 'Windows I/O trace failed; Linux report was saved.' }
        if ($EnableLinuxTracing) {
            if ($evidence.linuxTrace.timing.status -notin @('captured', 'no_matching_syscalls')) { throw 'Linux syscall timing unavailable; partial report was saved.' }
            if (@($evidence.linuxTrace.remainingTracers).Count -gt 0) { throw 'Tracer still present after capture; inspect the saved report.' }
        }
        if (-not @($evidence.samples | Where-Object { $_.pid }).Count) { throw 'No daemon snapshots collected; partial report was saved.' }
    } finally {
        # PLA also enforces a 20-second duration if this process is terminated.
        if ($windowsTrace.status -eq 'running') { Complete-WindowsIoTrace $windowsTrace }
        # A killed CLI can leave its container behind. Remove only the owned helper.
        try {
            $labels = (Invoke-DockerBounded "inspect --format `"{{json .Config.Labels}}`" $helper" '' 5) | ConvertFrom-Json
            if ($labels.'diagnostic.owner' -eq 'transmission-stall-capture') { [void](Invoke-DockerBounded "rm -f $helper" '' 5) }
        } catch { Write-Verbose 'Helper already removed or Docker unavailable.' }
    }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
