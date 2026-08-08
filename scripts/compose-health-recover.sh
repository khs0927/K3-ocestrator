#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.providers.yml}"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-$ROOT_DIR/.env}"
SERVICE="${SERVICE:-gateway}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-300}"
STATE_FILE="${RECOVERY_STATE_FILE:-$ROOT_DIR/data/provider-state/${SERVICE}-recovery.last}"
LOCK_DIR="${RECOVERY_LOCK_DIR:-$ROOT_DIR/data/provider-state/.${SERVICE}-recovery.lock}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 2
fi

mkdir -p "$(dirname "$STATE_FILE")"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "recovery check already running for $SERVICE"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

compose_args=(-f "$COMPOSE_FILE")
if [[ -f "$COMPOSE_ENV_FILE" ]]; then
  compose_args=(--env-file "$COMPOSE_ENV_FILE" "${compose_args[@]}")
fi

container_id="$(docker compose "${compose_args[@]}" ps -q "$SERVICE" | sed -n '1p')"
if [[ -z "$container_id" ]]; then
  echo "$SERVICE container is absent; starting it"
  docker compose "${compose_args[@]}" up -d "$SERVICE"
  exit 0
fi

status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
case "$status" in
  healthy|starting)
    echo "$SERVICE health=$status"
    exit 0
    ;;
  unhealthy|exited|dead)
    now="$(date +%s)"
    last="0"
    if [[ -r "$STATE_FILE" ]]; then
      read -r last < "$STATE_FILE" || last="0"
    fi
    if [[ "$last" =~ ^[0-9]+$ ]] && (( now - last < COOLDOWN_SECONDS )); then
      echo "$SERVICE health=$status; cooldown active"
      exit 1
    fi
    printf '%s\n' "$now" > "$STATE_FILE"
    echo "$SERVICE health=$status; restarting"
    docker compose "${compose_args[@]}" restart "$SERVICE"
    ;;
  *)
    echo "$SERVICE health=$status; no automatic action" >&2
    exit 1
    ;;
esac
