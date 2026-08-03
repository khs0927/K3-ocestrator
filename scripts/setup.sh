#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
python scripts/generate_key.py
mkdir -p data/kimi-code-home workspace config
[ -f config/provider-profiles.json ] || cp config/provider-profiles.example.json config/provider-profiles.json
[ -f config/routes.json ] || cp config/routes.example.json config/routes.json
printf '\nMulti-model gateway dependencies installed.\n'
printf 'Next: install Kimi Code, then run: kimi login\n'
