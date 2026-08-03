$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force workspace, data/kimi-code-home, data/sandbox-state | Out-Null
docker compose -f docker-compose.sandbox.yml up --build --abort-on-container-exit
