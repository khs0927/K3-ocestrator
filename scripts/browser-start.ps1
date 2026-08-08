Set-Location (Join-Path $PSScriptRoot "..")
$ErrorActionPreference = 'Stop'
& .\.venv\Scripts\python.exe -m browser_bridge.server
