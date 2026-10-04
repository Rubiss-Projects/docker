# VirtioFS presents Windows files as 1000:1000/777 even after chmod/chown.
# Protect only the new relay secret and its generated directory using NTFS ACLs.
$ErrorActionPreference = 'Stop'
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$principals = @($current, [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18'),
    [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
$targets = @(
    @{ Path = 'E:\Docker\caddy\channels-lan.env.secret'; Directory = $false },
    @{ Path = 'E:\Docker\swag\config\nginx\channels-lan-private'; Directory = $true }
)
foreach ($target in $targets) {
    if ($target.Directory -and -not (Test-Path -LiteralPath $target.Path)) {
        New-Item -ItemType Directory -Path $target.Path | Out-Null
    }
    $item = Get-Item -LiteralPath $target.Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
        [bool]$item.PSIsContainer -ne $target.Directory) { throw 'Unexpected relay key path type' }
    if ($target.Directory) {
        $acl = [System.Security.AccessControl.DirectorySecurity]::new()
        $inheritance = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    } else {
        $acl = [System.Security.AccessControl.FileSecurity]::new()
        $inheritance = [System.Security.AccessControl.InheritanceFlags]::None
    }
    $acl.SetOwner($current)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($principal in $principals) {
        $acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new(
            $principal, 'FullControl', $inheritance, 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $target.Path -AclObject $acl
    $actual = Get-Acl -LiteralPath $target.Path
    $rules = @($actual.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
    $expected = @($principals.Value | Sort-Object -Unique)
    $observed = @($rules.IdentityReference.Value | Sort-Object -Unique)
    if (-not $actual.AreAccessRulesProtected -or
        ($rules | Where-Object { $_.IsInherited -or $_.AccessControlType -ne 'Allow' }) -or
        @(Compare-Object $expected $observed).Count) { throw 'Relay key ACL verification failed' }
}
Write-Output 'Relay key Windows ACLs verified: current operator, SYSTEM and Administrators only'
