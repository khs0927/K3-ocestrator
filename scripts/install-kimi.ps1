$ErrorActionPreference = "Stop"
irm https://code.kimi.com/kimi-code/install.ps1 | iex
Write-Host "Kimi Code installed. Open a new PowerShell window if 'kimi' is not yet on PATH."
