#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m browser_bridge.login "${1:?usage: browser-login.sh deepseek|glm}"
