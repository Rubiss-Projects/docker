$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-trace.ps1')

# Exercise deletion boundaries with real files, but never start ETW in this test.
function Invoke-DiagnosticCommand { }
$fixture = Join-Path $PSScriptRoot ('trace-test-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory $fixture)
try {
    foreach ($i in 1..6) {
        $name = 'io-20260923T12000{0}000Z_000001.etl' -f $i
        $file = New-Item -ItemType File (Join-Path $fixture $name)
        $file.LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes($i)
    }
    foreach ($name in @('io-unrelated.etl', 'capture-existing.json', 'media.mkv')) {
        [void](New-Item -ItemType File (Join-Path $fixture $name))
    }
    $trace = Start-WindowsIoTrace $fixture '20260923T130000000Z'
    $owned = @(Get-ChildItem $fixture -Filter '*.etl' | Where-Object Name -Match '^io-\d{8}T\d{9}Z_\d+\.etl$')
    if ($owned.Count -ne 4) { throw 'Retention did not reserve exactly one slot' }
    if ($owned.Name -contains 'io-20260923T120001000Z_000001.etl') { throw 'Oldest trace was retained' }
    foreach ($name in @('io-unrelated.etl', 'capture-existing.json', 'media.mkv')) {
        if (-not (Test-Path (Join-Path $fixture $name))) { throw "Unrelated file deleted: $name" }
    }
    function Invoke-DiagnosticCommand { throw 'Injected logman failure' }
    try {
        $null = Start-WindowsIoTrace $fixture '20260923T140000000Z'
        throw 'Start incorrectly succeeded'
    } catch {
        if ($_.Exception.Message -ne 'Injected logman failure') { throw }
    }
    $failed = @{ status = 'failed'; error = 'Original failure' }
    Complete-WindowsIoTrace $failed
    if ($failed.error -ne 'Original failure') { throw 'Original failure was overwritten' }
    Write-Output 'PASS: retention boundaries, startup failure, failed-trace completion'
} finally { Remove-Item $fixture -Recurse -Force }
