# Run on Windows; real files/ACLs, no service or production watchdog execution.
[CmdletBinding()]
param([string]$Installer)
$ErrorActionPreference = 'Stop'
if (-not $Installer) { $Installer = Join-Path $PSScriptRoot 'install-watchdog.ps1' }
$root = Join-Path ([IO.Path]::GetTempPath()) ('caddy-watchdog-test-' + [Guid]::NewGuid().ToString('N'))
$access = [Security.AccessControl.AccessControlSections]::Access
function Require($condition, $message) { if (-not $condition) { throw $message } }
New-Item -ItemType Directory -Path (Join-Path $root 'Logs') -Force | Out-Null
$path = Join-Path $root 'start-docker-desktop.ps1'
$original = '        $exitCode = Invoke-DockerHealthMonitor'
try {
    [IO.File]::WriteAllText($path, $original)
    # Explicit private DACL exercises access-copying rather than directory inheritance.
    $acl = Get-Acl -LiteralPath $path
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'Allow'))
    Set-Acl -LiteralPath $path -AclObject $acl
    $before = (Get-Acl -LiteralPath $path).GetSecurityDescriptorSddlForm($access)
    $ownerBefore = (Get-Acl -LiteralPath $path).Owner
    & $Installer -Apply -ScriptsDirectory $root
    Require ((Get-Acl -LiteralPath $path).GetSecurityDescriptorSddlForm($access) -ceq $before) 'DACL changed'
    Require ((Get-Acl -LiteralPath $path).Owner -ceq $ownerBefore) 'Owner changed'
    $updated = [IO.File]::ReadAllText($path)
    Require ($updated.Contains('Invoke-CaddyPlexHealth -Repair')) 'Hook missing'
    $backups = @(Get-ChildItem -LiteralPath $root -Filter '*.before-caddy-*')
    Require ($backups.Count -eq 1) 'Expected one original'
    Require ([IO.File]::ReadAllText($backups[0].FullName) -ceq $original) 'Original changed'
    Require ((Get-Acl -LiteralPath $backups[0].FullName).GetSecurityDescriptorSddlForm($access) -ceq $before) 'Backup DACL changed'
    Require (@(Get-ChildItem -LiteralPath $root -Filter '*.caddy-candidate-*').Count -eq 0) 'Candidate leaked'
    & $Installer -Apply -ScriptsDirectory $root
    Require ([IO.File]::ReadAllText($path) -ceq $updated) 'Repeated install changed script'
    Require (@(Get-ChildItem -LiteralPath $root -Filter '*.before-caddy-*').Count -eq 1) 'Repeated install made backup'
    [IO.File]::WriteAllText($path, '# unsupported watchdog')
    $refused = $false
    try { & $Installer -Apply -ScriptsDirectory $root } catch { $refused = $true }
    Require $refused 'Changed watchdog accepted'
    Require ([IO.File]::ReadAllText($path) -ceq '# unsupported watchdog') 'Refusal changed original'
    # Inject only the rare ReplaceFile partial-move failure; all surrounding file
    # and ACL operations still execute against this disposable Windows directory.
    $partialInstaller = Join-Path $root 'partial-install.ps1'
    $source = [IO.File]::ReadAllText($Installer)
    $replaceCall = '[IO.File]::Replace($candidate, $path, $backup)'
    Require ([regex]::Matches($source, [regex]::Escape($replaceCall)).Count -eq 1) 'Replacement site changed'
    [IO.File]::WriteAllText($partialInstaller, $source.Replace($replaceCall, '[IO.File]::Move($path, $backup); throw "Injected partial replacement"'))
    [IO.File]::WriteAllText($path, $original)
    $refused = $false
    try { & $partialInstaller -Apply -ScriptsDirectory $root } catch { $refused = $true }
    Require $refused 'Partial replacement accepted'
    Require (-not (Test-Path -LiteralPath $path)) 'Partial fixture did not remove target'
    $candidates = @(Get-ChildItem -LiteralPath $root -Filter '*.caddy-candidate-*')
    Require ($candidates.Count -eq 1) 'Recovery candidate deleted'
    Require ([IO.File]::ReadAllText($candidates[0].FullName).Contains('Invoke-CaddyPlexHealth -Repair')) 'Recovery candidate incomplete'
    Require (@(Get-ChildItem -LiteralPath $root -Filter '*.before-caddy-*').Count -eq 2) 'Recovery backup missing'
    Write-Output 'Passed: DACL/owner/backup, idempotence, changed-source refusal, partial-replacement retention'
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
