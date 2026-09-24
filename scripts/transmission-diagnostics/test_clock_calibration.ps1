$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'clock-calibration.ps1')
# A synthetic guest clock 400 ms ahead must fall inside every reported bracket.
function Invoke-DockerBounded {
    return (([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + 400) * [long]1000000).ToString()
}
$result = Get-ClockCalibration
if ($result.status -ne 'bounded' -or $result.linuxMinusWindowsLowerMs -gt 400 -or $result.linuxMinusWindowsUpperMs -lt 400) {
    throw 'Known clock offset outside uncertainty bounds'
}
function Invoke-DockerBounded { throw 'Guest unavailable' }
$result = Get-ClockCalibration
if ($result.status -ne 'unavailable' -or $result.samples.Count -ne 3) { throw 'Calibration failure not retained' }
$before = @{ status = 'bounded'; linuxMinusWindowsLowerMs = 100; linuxMinusWindowsUpperMs = 200 }
$after = @{ status = 'bounded'; linuxMinusWindowsLowerMs = -200; linuxMinusWindowsUpperMs = -100 }
if ((Compare-ClockCalibration $before $after).status -ne 'offset_changed') { throw 'Clock change not detected' }
if ((Compare-ClockCalibration $before $before).status -ne 'consistent_endpoints') { throw 'Consistent endpoints not recognized' }
Write-Output 'Clock calibration tests passed'
