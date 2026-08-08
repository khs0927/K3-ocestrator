#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/install-kimi.sh
./scripts/setup.sh
if [ "${INSTALL_BROWSER_FALLBACK:-0}" = "1" ]; then
  ./scripts/setup-browser.sh
fi
printf '\nBootstrap complete. Next: ./scripts/login.sh && ./scripts/doctor.sh\n'
