#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KIMI_CODE_HOME="${KIMI_CODE_HOME:-$(pwd)/data/kimi-code-home}"
kimi login
