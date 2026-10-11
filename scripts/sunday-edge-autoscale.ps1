param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
. 'E:\Scripts\docker-desktop-common.ps1'
if (-not (Enter-DockerOperationLock)) {
    Write-Output '{"skipped":"Docker Desktop maintenance owns the lock"}'
    exit 0
}
try {
    $resources = $null
    try {
        # Two fresh raw samples avoid localized performance-counter names and
        # cached formatted readings. Counter failure blocks additions only.
        $before = Get-CimInstance Win32_PerfRawData_PerfOS_Processor -Filter "Name='_Total'"
        Start-Sleep -Seconds 1
        $after = Get-CimInstance Win32_PerfRawData_PerfOS_Processor -Filter "Name='_Total'"
        $elapsed = [double]$after.Timestamp_Sys100NS - [double]$before.Timestamp_Sys100NS
        $idle = [double]$after.PercentIdleTime - [double]$before.PercentIdleTime
        if ($elapsed -le 0 -or $idle -lt 0 -or $idle -gt $elapsed) { throw 'Invalid CPU sample' }
        $memory = Get-CimInstance Win32_OperatingSystem
        $system = Get-CimInstance Win32_ComputerSystem
        $resources = @{
            sampledAt = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            cpuCount = [int]$system.NumberOfLogicalProcessors
            cpuPercent = 100 * (1 - $idle / $elapsed)
            availableMemoryBytes = [long]$memory.FreePhysicalMemory * 1024
        }
    } catch {
        # The Linux controller still reconciles safe drains and existing work.
        $resources = $null
    }
    $arguments = @('-d', 'Ubuntu', '--', 'python3', '/mnt/e/Docker/scripts/sunday-edge-autoscale.py', '--windows-resources-stdin')
    if ($DryRun) { $arguments += '--dry-run' }
    ConvertTo-Json -InputObject $resources -Compress | & wsl.exe @arguments
    $result = $LASTEXITCODE
} finally {
    Exit-DockerOperationLock
}
exit $result
