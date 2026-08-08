#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p workspace data/kimi-code-home data/sandbox-state
chmod 700 data/kimi-code-home data/sandbox-state
exec docker compose -f docker-compose.sandbox.yml up --build --abort-on-container-exit
