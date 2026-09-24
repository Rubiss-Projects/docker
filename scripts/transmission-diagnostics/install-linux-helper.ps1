$ErrorActionPreference = 'Stop'
$docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$outputDir = 'E:\Scripts\Logs\transmission-stalls'
[void](New-Item -ItemType Directory -Path $outputDir -Force)
$temporary = Join-Path $outputDir ('linux-helper-' + [Guid]::NewGuid().ToString('N') + '.tmp')
try {
    # Build only during explicit installation, never during an incident.
    & $docker build --tag transmission-linux-timing:local --iidfile $temporary $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Diagnostic image build failed' }
    $image = (Get-Content -LiteralPath $temporary -Raw).Trim()
    if ($image -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Unexpected helper image identity' }
    & $docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 128m --pids-limit 16 --entrypoint strace $image --version
    if ($LASTEXITCODE -ne 0) { throw 'Diagnostic strace validation failed' }
    Move-Item -LiteralPath $temporary -Destination (Join-Path $outputDir 'linux-helper-image.txt') -Force
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
}
