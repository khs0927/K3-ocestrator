#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash
printf '\nKimi Code installed. Open a new shell if `kimi` is not yet on PATH.\n'
