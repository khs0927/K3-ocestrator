$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$env:KIMI_CODE_HOME = (Resolve-Path .\data\kimi-code-home).Path
kimi login
