$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'collect-wsl-memory.ps1')

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$sample = @'
MemTotal:       16321100 kB
MemFree:          100000 kB
MemAvailable:    7960844 kB
Buffers:          621540 kB
Cached:          7252688 kB
SReclaimable:     763560 kB
SwapTotal:       4194304 kB
SwapFree:        3739772 kB
some avg10=0.10 avg60=1.25 avg300=0.50 total=70281159
full avg10=0.00 avg60=0.01 avg300=0.01 total=62243467
'@

$line = ConvertTo-GuestMemoryMetric $sample
Assert-True ($line -match 'available_bytes=8151904256i(?:,|$)') 'kB conversion failed'
Assert-True ($line -match 'swap_used_bytes=465440768i(?:,|$)') 'Swap calculation failed'
Assert-True ($line -match 'pressure_some_avg60=1.25(?:,|$)') 'Pressure percentage changed'
Assert-True ($line -match 'pressure_full_total_us=62243467i(?:,|$)') 'Pressure total changed'

$oldCulture = [Threading.Thread]::CurrentThread.CurrentCulture
try {
    [Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('fr-FR')
    Assert-True ((ConvertTo-GuestMemoryMetric $sample) -ceq $line) 'Locale changed line protocol'
} finally { [Threading.Thread]::CurrentThread.CurrentCulture = $oldCulture }

$invalid = @(
    $sample.Replace('MemAvailable:', 'Unknown:'),
    ($sample + "`nMemAvailable: 123 kB"),
    $sample.Replace('full avg10=', 'unknown avg10='),
    $sample.Replace('avg60=1.25', 'avg60=101.25'),
    $sample.Replace('3739772 kB', '9999999 kB'),
    $sample.Replace('7960844 kB', '7960844 MB')
)
foreach ($text in $invalid) {
    $refused = $false
    try { $null = ConvertTo-GuestMemoryMetric $text } catch { $refused = $true }
    Assert-True $refused 'Invalid sample was accepted'
}

Write-Output 'Memory parser: byte conversion, swap, PSI, locale and six invalid-input cases passed.'
