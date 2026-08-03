#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
[ -f .env ] || cp .env.example .env
[ -f config/browser-profiles.json ] || cp config/browser-profiles.example.json config/browser-profiles.json
printf '\nOptional personal browser advisory bridge installed.\n'
printf 'Login manually with: ./scripts/browser-login.sh deepseek  (or glm)\n'
