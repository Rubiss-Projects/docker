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
    try {
        # Access rules are installed before any potentially secret-bearing bytes.
        # A different original owner also needs to be preserved, using normal UAC.
        $file = [IO.File]::Open($candidate, [IO.FileMode]::CreateNew); $file.Dispose()
        $access = [Security.AccessControl.AccessControlSections]::Access
        $originalAcl = Get-Acl -LiteralPath $path
        $dacl = $originalAcl.GetSecurityDescriptorSddlForm($access)
        $owner = $originalAcl.GetOwner([Security.Principal.SecurityIdentifier])
        $candidateAcl = [Security.AccessControl.FileSecurity]::new()
        $candidateAcl.SetSecurityDescriptorSddlForm($dacl, $access)
        Set-Acl -LiteralPath $candidate -AclObject $candidateAcl
        if ((Get-Acl -LiteralPath $candidate).GetSecurityDescriptorSddlForm($access) -cne $dacl) {
            throw 'Candidate access rules differ; no script bytes written'
        }
        $candidateAcl = Get-Acl -LiteralPath $candidate
        if ($candidateAcl.GetOwner([Security.Principal.SecurityIdentifier]) -ne $owner) {
            $ownerAcl = [Security.AccessControl.FileSecurity]::new()
            $ownerAcl.SetOwner($owner)
            try { Set-Acl -LiteralPath $candidate -AclObject $ownerAcl }
            catch { throw 'Preserving the watchdog owner requires an elevated PowerShell session; no script bytes written' }
        }
        if ((Get-Acl -LiteralPath $candidate).GetOwner([Security.Principal.SecurityIdentifier]) -ne $owner) {
            throw 'Candidate owner differs; no script bytes written'
        }
        [IO.File]::WriteAllText($candidate, $updated, [Text.UTF8Encoding]::new($false))
        # ReplaceFile preserves the target DACL and retains its original as backup.
        [IO.File]::Replace($candidate, $path, $backup)
    } finally {
        # ReplaceFile can move the original to backup before failing to move the
        # candidate. Keep both recovery files when the scheduled path is absent.
        if ((Test-Path -LiteralPath $path) -and (Test-Path -LiteralPath $candidate)) {
            Remove-Item -LiteralPath $candidate
        }
    }
    Write-Output "Caddy watchdog hook installed; original: $backup"
} finally { $lock.Dispose() }
