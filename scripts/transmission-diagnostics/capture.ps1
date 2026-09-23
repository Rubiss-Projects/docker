param([switch]$Install, [switch]$CaptureNow)
$ErrorActionPreference = 'Stop'
$taskName = 'Transmission stall diagnostics'
$outputDir = 'E:\Scripts\Logs\transmission-stalls'
$helper = 'transmission-stall-snapshot'
$docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'

if ($Install) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath)
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId 'Rubiss' -LogonType S4U -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Proc-only Transmission stall evidence; no service recovery or torrent mutations.' -Force | Out-Null
    exit 0
}

# Bound Docker CLI waits independently of the daemon and snapshot alarm.
function Invoke-DockerBounded([string]$Arguments, [string]$InputText = '', [int]$Seconds = 15) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $docker
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
            throw 'Docker diagnostic command timed out'
        }
        if ($process.ExitCode -ne 0) { throw ('Docker diagnostic command failed: ' + $stderr.Result) }
        return $stdout.Result
    } finally { $process.Dispose() }
}

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
    if ($image -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Unexpected image identity' }
    $source = Get-Content (Join-Path $PSScriptRoot 'snapshot.py') -Raw
    # Same local image: no pull, network, media/config mounts, Docker socket or
    # persistent daemon privileges. SYS_PTRACE permits proc syscall reads only
    # in this short-lived helper; the script never attaches to the daemon.
    try {
        $raw = Invoke-DockerBounded "run --rm -i --name $helper --label diagnostic.owner=transmission-stall-capture --pull never --network none --pid container:transmission --read-only --cap-drop ALL --cap-add SYS_PTRACE --cap-add DAC_READ_SEARCH --security-opt no-new-privileges --memory 64m --memory-swap 64m --pids-limit 16 --user 0 --entrypoint python3 $image -" $source 25
        if ($raw.Length -gt 1048576) { throw 'Snapshot exceeded 1 MiB bound' }
        $evidence = $raw | ConvertFrom-Json
        $report = @{ capturedAt = [DateTime]::UtcNow.ToString('o'); manualTest = [bool]$CaptureNow; state = $state; evidence = $evidence }
        $destination = Join-Path $outputDir ('capture-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.json')
        $report | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $destination -Encoding UTF8
        # Only our own diagnostic reports are rotated, never media or backups.
        Get-ChildItem $outputDir -Filter 'capture-*.json' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -Skip 20 | Remove-Item
        Write-Output $destination
    } finally {
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
