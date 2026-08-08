# Operations

## Startup sequence

1. Run setup/bootstrap.
2. Provision provider keys through root-only files or Docker Secrets; keep direct values in `.env` blank in production.
3. Run `kimi login` through `scripts/login.*`.
4. Run `scripts/doctor.*` and inspect available providers.
5. Start the gateway.
6. Send a `plan` request before enabling real changes.

### K3 API and self-hosted alternatives

The default K3 route is Kimi Code OAuth. If OAuth is unavailable, the gateway
can use the official OpenAI-compatible `kimi-k3` API with `KIMI_API_KEY` or a
root-only `KIMI_API_KEY_FILE`. The API profile is not available until
`provider-refresh` confirms the exact configured model.

For a self-hosted K3 server, set `K3_SELF_HOSTED_ENABLED=true` and point
`K3_SELF_HOSTED_BASE_URL` at the OpenAI-compatible vLLM/SGLang `/v1` endpoint.
The endpoint must advertise the exact `moonshotai/Kimi-K3` model. An API key,
when required by the server, may be supplied with `K3_SELF_HOSTED_API_KEY` or
`K3_SELF_HOSTED_API_KEY_FILE`. No DS2API account material is reused for either
K3 path.

The manual GitHub workflow also supports `kimi`; choose `kimi` with
`KIMI_API_KEY` configured in the `live-provider-gate` environment to run the
same exact-model and bounded synthetic-chat gate against the official API.

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

### Root-only Secret preparation on Ubuntu VPS

Create the deployment directory and verify its ownership before placing values
through the VPS Secret manager or an interactive root-only editor. Do not put
passwords in shell history or commit them:

```bash
sudo install -d -o root -g root -m 700 /etc/k3-secrets
for name in gateway-api-key ds2api-config.json ds2api-admin-key ds2api-jwt-secret ds2api-api-key provider.env gateway.env; do
  sudo install -o root -g root -m 600 /dev/null "/etc/k3-secrets/$name"
done
sudo stat -c '%U:%G %a %n' /etc/k3-secrets/*
```

The value in `ds2api-api-key` must exactly match one entry in the DS2API
config JSON Secret's `keys` array; it is the gateway-managed bearer key, not
the DeepSeek account password. The config Secret contains the account/session
material and is mounted only into DS2API. Provider API keys may use the
corresponding `*_API_KEY_FILE` settings and must remain outside Git.
Create `/etc/k3-secrets/provider.env` with the reviewed DS2API image digest and
the five host secret-file paths used by Compose, and set
`GATEWAY_ENV_FILE=/etc/k3-secrets/gateway.env` there. Keep provider API keys in
the root-only `gateway.env` (or an equivalent root-only secret manager), with
direct values blank when a provider is disabled. The recovery systemd template
uses these exact files, so it does not silently fall back to a missing project
`.env`.

## Docker Compose provider bundle

`docker-compose.providers.yml` keeps the gateway, DS2API, QA runner and watchdog on a private Compose network. The gateway and DS2API are exposed only through loopback; the DS2API admin surface is not published. Use an image built from the `ds2api-multi-provider` Secret-file branch (or a later reviewed commit); the public upstream `latest` image does not understand the `_FILE` variables used here. Before starting it, provide a pinned DS2API fork image and root-only secret files for both services:

```bash
export DS2API_IMAGE=ghcr.io/your-org/ds2api-multi-provider:pinned-sha
export GATEWAY_ENV_FILE=/etc/k3-secrets/gateway.env
export GATEWAY_API_KEY_FILE=/etc/k3-secrets/gateway-api-key
export DS2API_CONFIG_JSON_FILE=/etc/k3-secrets/ds2api-config.json
export DS2API_ADMIN_KEY_FILE=/etc/k3-secrets/ds2api-admin-key
export DS2API_JWT_SECRET_FILE=/etc/k3-secrets/ds2api-jwt-secret
export DS2API_API_KEY_FILE=/etc/k3-secrets/ds2api-api-key
docker compose -f docker-compose.providers.yml up -d
docker compose -f docker-compose.providers.yml --profile qa run --rm qa
```

The config secret is owned by DS2API and contains the DeepSeek account material; it is never mounted into the K3 gateway. The gateway receives only the DS2API managed API key from its separate secret file. The watchdog writes a redacted heartbeat every 30 seconds and exits on a failed check so its own `restart: unless-stopped` policy can recycle it. Docker does not restart a container merely because it is `unhealthy`, so install the host-level recovery helper below for the gateway.

Install the included root-only systemd template for both gateway and DS2API
on the VPS:

```bash
sudo install -d -o root -g root -m 700 /var/lib/k3-orchestrator
sudo cp deploy/k3-orchestrator-health-recover@.service /etc/systemd/system/
sudo cp deploy/k3-orchestrator-health-recover@.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now k3-orchestrator-health-recover@gateway.timer
sudo systemctl enable --now k3-orchestrator-health-recover@ds2api.timer
```

The helper restarts the named Compose service for `unhealthy`, `exited` or
`dead` state, uses a five-minute cooldown, and never prints Secret contents.
The persisted `/state/gateway-state.json` and Kimi session volume allow the
gateway to resume the session checkpoint after the container is restarted.

## Daily checks

- `GET /health` (process liveness)
- `GET /ready` (gateway readiness; requires Kimi Code and at least one available provider)
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
