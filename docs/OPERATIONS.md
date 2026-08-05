# Operations

## Startup sequence

1. Run setup/bootstrap.
2. Enter API keys in `.env`.
3. Run `kimi login` through `scripts/login.*`.
4. Run `scripts/doctor.*` and inspect available providers.
5. Start the gateway.
6. Send a `plan` request before enabling real changes.

### DS2API DeepSeek fallback

DS2API must be started and logged in separately. The gateway expects these local OpenAI-compatible endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /v1/models`
- `POST /v1/chat/completions`

Enable the fallback only after those checks pass:

```env
DS2API_ENABLED=true
DS2API_BASE_URL=http://127.0.0.1:5001/v1
DS2API_API_KEY=
```

The DeepSeek account password and login session belong to DS2API and must not be copied into this gateway, logs, prompts or GitHub. The gateway reuses the DS2API session; it does not re-login on every NVIDIA failure.

After starting a provider, verify its exact runtime model before using it:

```bash
curl -X POST http://127.0.0.1:8790/api/provider-refresh \
  -H "Authorization: Bearer YOUR_LOCAL_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"alias":"ds2api-deepseek-v4-flash"}'
```

The response must report `verified: true` and the expected `deepseek-v4-flash` model. NVIDIA GLM similarly requires `z-ai/glm-5.2` to appear in the authenticated NVIDIA `/v1/models` response; no GLM model downgrade is performed.

## Docker Compose provider bundle

`docker-compose.providers.yml` keeps the gateway, DS2API, QA runner and watchdog on a private Compose network. The gateway and DS2API are exposed only through loopback; the DS2API admin surface is not published. Before starting it, provide a pinned DS2API fork image and root-only secret files:

```bash
export DS2API_IMAGE=ghcr.io/your-org/ds2api-multi-provider:pinned-sha
export DS2API_CONFIG_JSON_FILE=/etc/k3-secrets/ds2api-config.json
export DS2API_ADMIN_KEY_FILE=/etc/k3-secrets/ds2api-admin-key
export DS2API_API_KEY_FILE=/etc/k3-secrets/ds2api-api-key
docker compose -f docker-compose.providers.yml up -d
docker compose -f docker-compose.providers.yml --profile qa run --rm qa
```

The config secret is owned by DS2API and contains the DeepSeek account material; it is never mounted into the K3 gateway. The gateway receives only the DS2API managed API key from its separate secret file. The watchdog writes a redacted heartbeat every 30 seconds; container restart policies and the persisted Kimi/state volumes allow recovery from a process restart. A VPS host-level monitor must restart an unhealthy gateway container if Docker health status remains failing.

## Daily checks

- `GET /health`
- `GET /api/providers`
- inspect `data/audit.jsonl`
- verify workspace allowlist
- keep `ALLOW_YOLO_MODE=false` unless isolated

## When NVIDIA is limited

The first 429/503/capacity failure opens its circuit temporarily. A 429 is retried at most once and honors `Retry-After`. Each request has at most three total provider attempts. A new stateless request falls through to the next route; a persistent session remains bound to its original provider, so create a new session to change providers. 404/410 disables only that model until a refresh, while 401/403 pauses that provider.

## Browser advisory recovery

Run the browser bridge only after manual login. Keep the browser visible for easier challenge handling. If selectors stop working, update `config/browser-profiles.json`. Never automate CAPTCHA or copy browser cookies into remote servers.

## Remote Minis

Run the gateway on the machine holding Kimi OAuth/browser sessions and expose it to Minis through SSH:

```bash
ssh -N -R 8790:127.0.0.1:8790 USER@MINIS_SERVER
```

Do not bind the local gateway directly to the public internet.

## Backups

Back up only configuration templates and source. Treat `.env`, `data/kimi-code-home`, browser profiles, session state and audit logs as secrets. Do not put them in repository history.
