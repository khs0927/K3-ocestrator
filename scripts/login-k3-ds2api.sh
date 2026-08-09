#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KIMI_CODE_HOME="${KIMI_CODE_HOME:-$(pwd)/data/kimi-code-home}"
printf '%s\n' 'Kimi K3 DS2API-compatible login: complete the official Kimi OAuth device flow in your browser.'
printf '%s\n' 'No password, token, or cookie is written to this project or sent to Minis.'
exec kimi login
