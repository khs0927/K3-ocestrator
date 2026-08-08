$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
& .\.venv\Scripts\python.exe -m playwright install chromium
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path config\browser-profiles.json)) { Copy-Item config\browser-profiles.example.json config\browser-profiles.json }
Write-Host "Optional personal browser advisory bridge installed."
Write-Host "Login manually with: .\scripts\browser-login.ps1 deepseek  (or glm)"
