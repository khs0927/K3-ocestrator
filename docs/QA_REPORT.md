# K3 provider fallback QA report

## Deterministic evidence

Executed in the K3 worktree:

```text
./.venv/bin/python -m pytest -q                 PASS: 51 passed
./scripts/validate.sh                           PASS: validation passed
./.venv/bin/python -m compileall -q app browser_bridge scripts   PASS
python3 -m json.tool config/provider-profiles.example.json       PASS
python3 -m json.tool config/routes.example.json                  PASS
git diff --check                                      PASS
FastAPI/MCP import and provider route registration                   PASS
```

The mock provider gate verifies DS2API `healthz`, `readyz` and exact
`deepseek-v4-flash` discovery. The failure-injection tests cover 429 retry,
three-attempt bounds, 503 circuit behavior, 404/410 permanent model disable,
secret-file binding, response reasoning/tool-call metadata, upstream model
identity, numeric/HTTP-date `Retry-After` handling, Kimi API exact model
discovery, and API_KEY_FILE direct-value precedence.
The security boundary tests also verify recursive audit-payload redaction for
Bearer, API-key, password, token, and header-shaped credential strings.
The adversarial review additions cover streaming NVIDIA-to-DS2API fallback,
structured stream redaction, provider:model circuit sharing, timeout and full
5xx classification, real HTTP Retry-After headers, empty tool/reasoning-only
responses, and DS2API model-boundary enforcement.
The live-gate contract tests exercise the DS2API health/readiness/model probes,
ten synthetic chat iterations, exact-model fail-closed behavior, and explicit
NVIDIA DeepSeek Flash to DS2API candidate ordering.
The settings/Compose tests cover root-only gateway, DS2API admin/JWT/API-key
secret-file wiring and successful `docker compose config` rendering with the
example environment and placeholder paths.
The watchdog tests confirm direct-secret precedence and root-only file fallback;
the Compose healthcheck reads the mounted gateway Secret when no direct key is
present, and the watchdog exits on failed health when deployed with
`--fail-fast`; `scripts/compose-health-recover.sh` provides the host-level
unhealthy-container recovery path.
The validation script also rejects mutable GitHub Action tags; the current
workflow SHAs are recorded in `docs/CI_SHA_MANIFEST.md`.

## Hosted evidence

- K3 PR #1: <https://github.com/khs0927/K3-ocestrator/pull/1>
- Public Actions run for implementation head `0f8dd10`: <https://github.com/khs0927/K3-ocestrator/actions/runs/31280427961>
- PR Actions run for implementation head `0f8dd10`: <https://github.com/khs0927/K3-ocestrator/actions/runs/31280429595>
- Python 3.11: passed
- Python 3.13: passed
- K3 implementation head covered by the evidence above: `0f8dd10`
- Compose auth healthcheck fix: `556237d`
- Security/error-boundary and explicit-fallback tests: `fdd32fe` plus the current branch head
- DS2API config Secret PR: <https://github.com/khs0927/ds2api-multi-provider/pull/2>
- DS2API latest Secret-file consistency commit: `291ed32`
- DS2API local Go evidence: `go1.26.5 go test ./...` and `go vet ./...` passed;
  remote Quality Gates also passed: <https://github.com/khs0927/ds2api-multi-provider/actions/runs/31279315631>.
- Kimi API live gate workflow: supports exact `kimi-k3` discovery and bounded
  synthetic chat using the `live-provider-gate` environment's `KIMI_API_KEY`.

## Negative/live boundary evidence

The local live gate and watchdog were run without a DS2API service. They failed
closed with a redacted connection error and emitted no credential or response
body. This proves the disabled/unreachable safety behavior, not live success.

No Kimi OAuth session, NVIDIA key, Z.AI key, DS2API account, authorized VPS or
pinned fork image was available in this environment. Therefore the following
remain unclaimed:

- ten live synthetic chats per enabled provider;
- NVIDIA DeepSeek V4 Flash overload injection and DS2API failover;
- DS2API outage and next-provider failover;
- real K3 tool/permission/edit cycle;
- VPS restart, watchdog recovery and checkpoint continuation.

## Go/no-go

Offline implementation gate: **GO**.

Production gate: **NO-GO** until the operator-side live and VPS evidence above
is captured. The repository includes the manual workflow and Compose template
to collect that evidence without placing passwords in GitHub or K3 logs.
