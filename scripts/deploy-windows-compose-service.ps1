param (
    [Parameter(Mandatory = $true)][string]$ServiceDirectory,
    [string]$StartStopped = "false",
    [string]$DryRun = "false"
)

$ErrorActionPreference = "Stop"
$dockerCli = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$shouldStartStopped = $StartStopped -match '^(?i:true|1|yes|on)$'
$isDryRun = $DryRun -match '^(?i:true|1|yes|on)$'

if (-not (Test-Path $dockerCli)) {
    throw "Docker CLI not found at $dockerCli"
}
if (-not (Test-Path (Join-Path $ServiceDirectory "docker-compose.yml"))) {
    throw "Compose file not found in $ServiceDirectory"
}

$envArgs = @()
foreach ($envFile in @(".env", ".env.secret")) {
    $envPath = Join-Path $ServiceDirectory $envFile
    if (Test-Path $envPath) {
        $envArgs += @("--env-file", $envPath)
    }
}
$composeArgs = @("compose") + $envArgs + @("--project-directory", $ServiceDirectory, "-f", (Join-Path $ServiceDirectory "docker-compose.yml"))

function Invoke-Compose {
    param ([Parameter(Mandatory = $true)][string[]]$Arguments)

    if ($isDryRun) {
        Write-Host "DRY RUN: docker $($Arguments -join ' ')"
        return
    }

    & $dockerCli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Invoke-Compose -Arguments ($composeArgs + @("config", "--quiet"))

if (-not $isDryRun -and -not $shouldStartStopped) {
    $runningServices = & $dockerCli @composeArgs "ps" "--status" "running" "--services"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to determine running Compose services in $ServiceDirectory"
    }
    if ([string]::IsNullOrWhiteSpace(($runningServices -join "`n"))) {
        Write-Host "Skipping $ServiceDirectory because it has no currently running Compose services"
        exit 0
    }
}

Invoke-Compose -Arguments ($composeArgs + @("pull", "--ignore-buildable"))
Invoke-Compose -Arguments ($composeArgs + @("up", "-d", "--build", "--remove-orphans"))
