# Read the shared WSL kernel through the existing cAdvisor container. This does
# not launch a WSL distro, start Docker, access payloads, or reclaim memory.
[CmdletBinding()]
param([string]$Docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe')

$ErrorActionPreference = 'Stop'

function Read-GuestMemory {
    param([string]$Executable)

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = [Diagnostics.ProcessStartInfo]@{
        FileName = $Executable
        Arguments = '--host npipe:////./pipe/dockerDesktopLinuxEngine exec cadvisor cat /proc/meminfo /proc/pressure/memory'
        UseShellExecute = $false
        CreateNoWindow = $true
        RedirectStandardOutput = $true
        RedirectStandardError = $true
    }
    try {
        if (-not $process.Start()) { throw 'Memory reader did not start' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(4000)) {
            # Terminate only this owned, read-only Docker CLI, never a container.
            $process.Kill()
            [void]$process.WaitForExit(1000)
            throw 'Memory reader timed out'
        }
        if (-not $stdout.Wait(500) -or -not $stderr.Wait(500)) { throw 'Memory reader streams did not settle' }
        if ($process.ExitCode -ne 0) { throw 'Memory reader failed' }
        return $stdout.Result
    } finally {
        $process.Dispose()
    }
}

function ConvertTo-GuestMemoryMetric {
    param([Parameter(Mandatory)][string]$Text)

    $culture = [Globalization.CultureInfo]::InvariantCulture
    $values = [ordered]@{ collect_up = '1i' }
    $memory = @{}
    $fields = [ordered]@{
        MemTotal = 'total_bytes'
        MemAvailable = 'available_bytes'
        MemFree = 'free_bytes'
        Cached = 'cached_bytes'
        Buffers = 'buffers_bytes'
        SReclaimable = 'reclaimable_slab_bytes'
        SwapTotal = 'swap_total_bytes'
        SwapFree = 'swap_free_bytes'
    }
    foreach ($key in $fields.Keys) {
        $matches = [regex]::Matches($Text, "(?m)^${key}:[ \t]+([0-9]+)[ \t]+kB[ \t]*\r?$")
        if ($matches.Count -ne 1) { throw "Missing or duplicate memory field: $key" }
        $bytes = [long]([long]::Parse($matches[0].Groups[1].Value, $culture) * 1024)
        $memory[$key] = $bytes
        $values[$fields[$key]] = $bytes.ToString($culture) + 'i'
    }
    if ($memory.MemTotal -le 0 -or $memory.MemAvailable -gt $memory.MemTotal -or $memory.SwapFree -gt $memory.SwapTotal) {
        throw 'Inconsistent memory counters'
    }
    $values['swap_used_bytes'] = ([long]($memory.SwapTotal - $memory.SwapFree)).ToString($culture) + 'i'

    foreach ($kind in @('some', 'full')) {
        $matches = [regex]::Matches($Text, "(?m)^$kind avg10=([0-9.]+) avg60=([0-9.]+) avg300=([0-9.]+) total=([0-9]+)\r?$")
        if ($matches.Count -ne 1) { throw "Missing or duplicate memory pressure: $kind" }
        $windows = @(10, 60, 300)
        for ($i = 0; $i -lt $windows.Count; $i++) {
            $value = [double]::Parse($matches[0].Groups[$i + 1].Value, $culture)
            if ($value -lt 0 -or $value -gt 100) { throw 'Invalid pressure percentage' }
            $values["pressure_${kind}_avg$($windows[$i])"] = $value.ToString('R', $culture)
        }
        $values["pressure_${kind}_total_us"] = ([long]::Parse($matches[0].Groups[4].Value, $culture)).ToString($culture) + 'i'
    }

    $parts = foreach ($entry in $values.GetEnumerator()) { $entry.Key + '=' + $entry.Value }
    return 'wsl_memory,scope=shared_kernel ' + ($parts -join ',')
}

# Dot-sourcing exposes the parser for focused tests without a Docker operation.
if ($MyInvocation.InvocationName -ne '.') {
    try {
        ConvertTo-GuestMemoryMetric -Text (Read-GuestMemory -Executable $Docker)
    } catch {
        # Missing data is not zero pressure/free RAM. Keep a separate up signal.
        Write-Output 'wsl_memory,scope=shared_kernel collect_up=0i'
        [Console]::Error.WriteLine('WSL memory collection failed; guest counters omitted.')
    }
}
