# Operations

## Startup sequence

1. Run setup/bootstrap.
2. Enter API keys in `.env`.
3. Run `kimi login` through `scripts/login.*`.
4. Run `scripts/doctor.*` and inspect available providers.
5. Start the gateway.
6. Send a `plan` request before enabling real changes.

## Daily checks

- `GET /health`
- `GET /api/providers`
- inspect `data/audit.jsonl`
- verify workspace allowlist
- keep `ALLOW_YOLO_MODE=false` unless isolated

## When NVIDIA is limited

The first 429/503/capacity failure opens its circuit temporarily. A new stateless request falls through to the next route. A persistent session remains bound to its original provider; create a new session to change providers.

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
