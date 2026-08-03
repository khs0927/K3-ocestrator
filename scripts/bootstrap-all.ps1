param([switch]$InstallBrowserFallback)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
& .\scripts\install-kimi.ps1
& .\scripts\setup.ps1
if ($InstallBrowserFallback) { & .\scripts\setup-browser.ps1 }
Write-Host "Bootstrap complete. Next: .\scripts\login.ps1 ; .\scripts\doctor.ps1"
