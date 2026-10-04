# Install only the Caddy post-check; hold the watchdog's existing operation lock.
[CmdletBinding()]
param([switch]$Apply, [string]$ScriptsDirectory = 'E:\Scripts')
$ErrorActionPreference = 'Stop'
$path = Join-Path $ScriptsDirectory 'start-docker-desktop.ps1'
$lockPath = Join-Path $ScriptsDirectory 'Logs\docker-health-monitor.lock'
$hookPath = 'E:\Docker\caddy\watchdog.ps1'
$old = '        $exitCode = Invoke-DockerHealthMonitor'
$new = @'
        $exitCode = Invoke-DockerHealthMonitor
        # Native Caddy has independent remediation: never classify it as a Docker failure.
        if ($exitCode -eq 0 -and -not (Test-MaintenanceWindow)) {
            . 'E:\Docker\caddy\watchdog.ps1'
            if (-not (Invoke-CaddyPlexHealth -Repair)) { $exitCode = 1 }
        }
'@
$lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $original = [IO.File]::ReadAllText($path)
    $newline = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }
    $replacement = $new.Replace("`r`n", "`n").Replace("`n", $newline)
    if ($original.Contains($replacement)) { Write-Output 'Caddy watchdog hook already installed'; return }
    if ([regex]::Matches($original, [regex]::Escape($old)).Count -ne 1) { throw 'Watchdog source changed; no modification made' }
    if (-not (Test-Path -LiteralPath $hookPath)) { throw 'Reviewed hook must exist on main before installation' }
    $updated = $original.Replace($old, $replacement)
    $tokens = $null; $parseErrors = $null
    [Management.Automation.Language.Parser]::ParseInput($updated, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) { throw 'Candidate watchdog syntax invalid' }
    if (-not $Apply) { Write-Output 'Caddy watchdog hook validated; use -Apply to install'; return }
    $suffix = [Guid]::NewGuid().ToString('N')
    $candidate = $path + '.caddy-candidate-' + $suffix
    $backup = $path + '.before-caddy-' + $suffix
    # Preserve the original ACL before writing potentially secret-bearing script bytes.
    $file = [IO.File]::Open($candidate, [IO.FileMode]::CreateNew); $file.Dispose()
    Set-Acl -LiteralPath $candidate -AclObject (Get-Acl -LiteralPath $path)
    [IO.File]::WriteAllText($candidate, $updated, [Text.UTF8Encoding]::new($false))
    [IO.File]::Replace($candidate, $path, $backup)
    Write-Output "Caddy watchdog hook installed; original: $backup"
} finally { $lock.Dispose() }
