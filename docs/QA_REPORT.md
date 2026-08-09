# K3 provider fallback QA report

## Deterministic evidence

Executed in the K3 worktree:

```text
./.venv/bin/python -m pytest -q                 PASS: 77 passed
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
responses, DS2API model-boundary enforcement, and shared provider:model
concurrency/min-interval locks. Streaming tests also ensure that a provider
cannot be swapped after partial output has reached the client.
The live-gate contract tests exercise the DS2API health/readiness/model probes,
ten synthetic chat iterations, exact-model fail-closed behavior, and explicit
NVIDIA DeepSeek Flash to DS2API candidate ordering.
The OpenAI-compatible K3 contract tests verify all top-level
`reasoning_effort` values, upstream model identity, non-stream reasoning/tool
metadata, and stream round-trip without duplicate aggregate deltas.
ACP contract tests also fail closed for unsupported/unapplied thought-level
values, preserve structured assistant reasoning/tool history in flattened
multi-turn prompts, and restore persisted reasoning effort after restart.
Security tests cover ACP runtime key variants, custom DS2API provider identity
health probes, safe public catalog URLs, and rejected metadata reasoning values.
Partial-stream tests cover message, thought, and tool events before a provider
failure and prove that no fallback response is mixed into any of them.
The release-gate tests require an ACP reasoning option advertisement and an
explicit post-update current-value confirmation; missing or mismatched values
fail closed.
The K3 compatibility tests verify that the client-facing `kimi-k3` request name
resolves to the official OAuth-backed `k3` runtime, is advertised by `/v1/models`,
and reaches the MCP/OpenAI request path without treating K3 as a DeepSeek DS2API
model.
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

- K3 hardening PR #5: <https://github.com/khs0927/K3-ocestrator/pull/5>
- K3 hardening head `6903ed0`; push CI: <https://github.com/khs0927/K3-ocestrator/actions/runs/31317890602>
- K3 hardening PR CI: <https://github.com/khs0927/K3-ocestrator/actions/runs/31317809201>
- K3 hardening merge commit `3dffc85`; post-merge main CI: <https://github.com/khs0927/K3-ocestrator/actions/runs/31318345818>
- Python 3.11: passed
- Python 3.13: passed
- DS2API config Secret PR #2 is merged at `8c65bd2`: <https://github.com/khs0927/ds2api-multi-provider/pull/2>
- DS2API post-merge Quality Gates passed: <https://github.com/khs0927/ds2api-multi-provider/actions/runs/31282317212>
- DS2API local Go evidence: `go1.26.5 go test ./...` and `go vet ./...` passed.
- Kimi API live gate workflow: supports exact `kimi-k3` discovery and bounded
  synthetic chat using the `live-provider-gate` environment's `KIMI_API_KEY`.

The hosted CI evidence above is offline/static CI evidence. The manual
`live-provider-gate` workflow has not been run because its required provider
secrets and DS2API endpoint variable are not configured.

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
