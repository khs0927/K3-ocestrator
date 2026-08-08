#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi

"$PYTHON_BIN" -m pytest -q
"$PYTHON_BIN" -m compileall -q app browser_bridge scripts tests

while IFS= read -r -d '' file; do
  bash -n "$file"
done < <(find scripts -type f -name '*.sh' -print0)

while IFS= read -r -d '' file; do
  "$PYTHON_BIN" -m json.tool "$file" >/dev/null
done < <(find config -type f -name '*.json' -print0)

git diff --check

# Detect common provider/GitHub credential formats in tracked implementation files.
# Fixtures, documentation and examples intentionally contain redaction test values.
if git grep -nI -E '(nvapi-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})' -- \
  ':(exclude)tests/**' ':(exclude)docs/**' ':(exclude).env.example'; then
  echo "secret scan failed: credential-shaped value found in implementation files" >&2
  exit 1
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/k3-compose-XXXXXX")"
  trap 'rm -rf "$COMPOSE_TMP"' EXIT
  touch "$COMPOSE_TMP/gateway-api-key" \
    "$COMPOSE_TMP/ds2api-config.json" \
    "$COMPOSE_TMP/ds2api-admin-key" \
    "$COMPOSE_TMP/ds2api-jwt-secret" \
    "$COMPOSE_TMP/ds2api-api-key"
  GATEWAY_ENV_FILE=.env.example \
  DS2API_IMAGE=ghcr.io/example/ds2api-multi-provider@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  GATEWAY_API_KEY_FILE="$COMPOSE_TMP/gateway-api-key" \
  DS2API_CONFIG_JSON_FILE="$COMPOSE_TMP/ds2api-config.json" \
  DS2API_ADMIN_KEY_FILE="$COMPOSE_TMP/ds2api-admin-key" \
  DS2API_JWT_SECRET_FILE="$COMPOSE_TMP/ds2api-jwt-secret" \
  DS2API_API_KEY_FILE="$COMPOSE_TMP/ds2api-api-key" \
    docker compose --env-file .env.example -f docker-compose.providers.yml config --quiet
else
  echo "docker compose unavailable; skipped provider Compose render" >&2
fi

echo "validation passed"
