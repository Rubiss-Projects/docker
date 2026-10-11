param ([switch]$ValidateOnly)
# Compatibility entry point: routine nightly restarts are retired. Even if the
# old task is enabled manually, use the same evidence-based recovery policy.
& (Join-Path $PSScriptRoot 'start-docker-desktop.ps1') -ValidateOnly:$ValidateOnly
exit $LASTEXITCODE
