param([Parameter(Mandatory=$true)][ValidateSet('deepseek','glm')][string]$Provider)
Set-Location (Join-Path $PSScriptRoot "..")
$ErrorActionPreference = 'Stop'
& .\.venv\Scripts\python.exe -m browser_bridge.login $Provider
