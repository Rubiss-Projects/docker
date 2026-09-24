# Docker and Windows UTC are different clocks. Bracket guest time with host time
# and preserve uncertainty instead of treating a midpoint as an exact offset.
function Compare-ClockCalibration($Before, $After) {
    $status = 'uncertain'
    if ($Before.status -eq 'bounded' -and $After.status -eq 'bounded') {
        $lower = [Math]::Max($Before.linuxMinusWindowsLowerMs, $After.linuxMinusWindowsLowerMs)
        $upper = [Math]::Min($Before.linuxMinusWindowsUpperMs, $After.linuxMinusWindowsUpperMs)
        $status = if ($lower -le $upper) { 'consistent_endpoints' } else { 'offset_changed' }
    }
    # Even overlapping endpoints cannot exclude an intervening clock step.
    return @{ status = $status; before = $Before; after = $After }
}

function Get-ClockCalibration {
    $samples = @()
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        $before = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $watch = [Diagnostics.Stopwatch]::StartNew()
        try {
            $raw = Invoke-DockerBounded 'exec transmission python3 -c "import time; print(time.time_ns())"' '' 2
            $after = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            $watch.Stop()
            $guestNs = [long]::Parse($raw.Trim(), [Globalization.CultureInfo]::InvariantCulture)
            $guestMs = $guestNs / 1000000.0
            $samples += @{ windowsBeforeMs = $before; windowsAfterMs = $after; linuxNs = $guestNs;
                roundTripMs = $watch.Elapsed.TotalMilliseconds;
                lowerOffsetMs = $guestMs - $after - 1; upperOffsetMs = $guestMs - $before + 1;
                clockJump = [Math]::Abs(($after - $before) - $watch.Elapsed.TotalMilliseconds) -gt 5 }
        } catch {
            $samples += @{ error = $_.Exception.Message }
        }
    }
    $valid = @($samples | Where-Object { $_.ContainsKey('lowerOffsetMs') -and -not $_.clockJump })
    if ($valid.Count -eq 0) { return @{ status = 'unavailable'; samples = $samples } }
    $lower = ($valid | ForEach-Object { $_.lowerOffsetMs } | Measure-Object -Maximum).Maximum
    $upper = ($valid | ForEach-Object { $_.upperOffsetMs } | Measure-Object -Minimum).Minimum
    $status = if ($lower -le $upper -and $valid.Count -eq 3) { 'bounded' } else { 'uncertain' }
    return @{ status = $status; linuxMinusWindowsLowerMs = $lower; linuxMinusWindowsUpperMs = $upper; samples = $samples }
}
