$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
& .\.venv\Scripts\python.exe scripts\generate_key.py
New-Item -ItemType Directory -Force -Path data\kimi-code-home, workspace, config | Out-Null
if (-not (Test-Path config\provider-profiles.json)) { Copy-Item config\provider-profiles.example.json config\provider-profiles.json }
if (-not (Test-Path config\routes.json)) { Copy-Item config\routes.example.json config\routes.json }
Write-Host "Multi-model gateway dependencies installed."
Write-Host "Next: install Kimi Code, then run: kimi login"
