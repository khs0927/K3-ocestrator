# Disposable container execution baseline

This profile is the minimum isolation baseline for `execute`. It is not a proof that arbitrary model-generated commands are safe.

## Guarantees provided

- non-root UID 10001
- read-only container root filesystem
- all Linux capabilities dropped
- `no-new-privileges`
- loopback-only host port binding
- one writable project mount: `./workspace` → `/workspace`
- separate writable Kimi OAuth/session and gateway state mounts
- no host home, SSH directory, Docker socket, cloud credentials, or Git credential store mounted
- process, memory, CPU and temporary filesystem limits
- YOLO disabled

## Network caveat

Kimi OAuth and remote model APIs require outbound network access. Docker Compose cannot express a reliable domain allowlist by itself. Enforce egress at the host firewall, proxy, or a dedicated Docker network gateway. Start with only the domains required by the enabled providers. Do not expose port 8790 beyond host loopback.

## Start

1. Copy `.env.example` to `.env` and generate strong local keys.
2. Put only the disposable target repository under `./workspace`.
3. Build and start:

```bash
docker compose -f docker-compose.sandbox.yml build
docker compose -f docker-compose.sandbox.yml run --rm orchestrator kimi login
docker compose -f docker-compose.sandbox.yml up --abort-on-container-exit
```

The OAuth directory persists at `./data/kimi-code-home`; protect and back it up as a secret. Stop and delete the container after the task. Review `./data/sandbox-state/audit.jsonl` and the workspace diff before committing.

## Forbidden additions

Do not mount any of the following into the container:

- `/var/run/docker.sock`
- the user's home directory
- `~/.ssh`, cloud credential directories, browser profiles, or password stores
- arbitrary parent directories above the target repository
- a privileged device or `--privileged`
