param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
. 'E:\Scripts\docker-desktop-common.ps1'
if (-not (Enter-DockerOperationLock)) {
    Write-Output '{"skipped":"Docker Desktop maintenance owns the lock"}'
    exit 0
}
try {
    $arguments = @('-d', 'Ubuntu', '--', 'python3', '/mnt/e/Docker/scripts/sunday-edge-autoscale.py')
    if ($DryRun) { $arguments += '--dry-run' }
    & wsl.exe @arguments
    $result = $LASTEXITCODE
} finally {
    Exit-DockerOperationLock
}
exit $result
