$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not $env:KIMI_CODE_HOME) { $env:KIMI_CODE_HOME = (Join-Path (Get-Location) "data\kimi-code-home") }
Write-Host "Kimi K3 DS2API-compatible login: complete the official Kimi OAuth device flow in your browser."
Write-Host "No password, token, or cookie is written to this project or sent to Minis."
kimi login
