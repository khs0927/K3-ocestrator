#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
gateway_url="${GATEWAY_URL:-http://127.0.0.1:8790}"
api_key="${GATEWAY_API_KEY:-}"
if [[ -z "$api_key" && -n "${GATEWAY_API_KEY_FILE:-}" ]]; then
  api_key="$(<"$GATEWAY_API_KEY_FILE")"
fi
api_key="${api_key//$'\n'/}"
if [[ -z "$api_key" ]]; then
  printf '%s\n' 'GATEWAY_API_KEY or GATEWAY_API_KEY_FILE is required.' >&2
  exit 2
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
auth_header="Authorization: Bearer $api_key"

request() {
  local name="$1"
  local method="$2"
  local url="$3"
  local body="${4:-}"
  local status
  if [[ -n "$body" ]]; then
    status="$(curl -sS -o "$tmp_dir/$name.json" -w '%{http_code}' -X "$method" "$url" -H "$auth_header" -H 'Content-Type: application/json' --data "$body")"
  else
    status="$(curl -sS -o "$tmp_dir/$name.json" -w '%{http_code}' -X "$method" "$url" -H "$auth_header")"
  fi
  if [[ "$status" != 200 ]]; then
    printf '%s\n' "$name failed with HTTP $status" >&2
    exit 1
  fi
}

request healthz GET "$gateway_url/healthz"
request readyz GET "$gateway_url/readyz"
request models GET "$gateway_url/v1/models"

python3 - "$tmp_dir/models.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
rows = payload.get("data", [])
match = next((row for row in rows if row.get("id") == "kimi-k3"), None)
if not match or match.get("runtime_model") != "k3":
    raise SystemExit("kimi-k3 was not advertised as runtime_model k3")
PY

request chat POST "$gateway_url/v1/chat/completions" '{"model":"kimi-k3","messages":[{"role":"user","content":"Reply with the single word OK."}],"reasoning_effort":"high","metadata":{"mode":"plan","allow_fallback":false}}'

python3 - "$tmp_dir/chat.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
if payload.get("provider") != "ds2api-kimi-k3":
    raise SystemExit("chat did not use ds2api-kimi-k3")
if payload.get("upstream_model") != "k3":
    raise SystemExit("chat did not use upstream model k3")
print("K3 DS2API-compatible smoke passed: kimi-k3 -> ds2api-kimi-k3 -> k3")
PY
