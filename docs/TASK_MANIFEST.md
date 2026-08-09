# K3 multi-provider task manifest

This manifest is the handoff contract for the K3 orchestrator. Agents do not
write the same file concurrently; review and QA are independent of the agent
that implemented the change.

| Role | Scope | Current evidence | Status |
|---|---|---|---|
| Central K3 orchestrator | task graph, checkpoint/state, final integration | `app/manager.py`, `app/providers.py`, branch `agent/kimi-k3-ds2api-account` | K3 compatibility implementation in review |
| Compatibility researcher | K3, DS2API, NVIDIA GLM exact IDs and endpoint boundaries | `docs/PROVIDER_STRATEGY.md`, `docs/COMPATIBILITY.md` | complete |
| Provider designer | common profile, discovery, circuit and bounded retry contract | `app/providers.py`, `app/models.py` | complete |
| DS2API Go agent | DeepSeek-only upstream and Secret-file boundary | `ds2api-multi-provider` PR #2, merged `8c65bd2` | local Go test/vet and post-merge Quality Gates run `31282317212` pass |
| K3 Python agent | ACP provider routing, K3 OAuth/DS2API-compatible model name, DS2API fallback, K3 API/self-hosted profiles, MCP/API tools, stream metadata | `ds2api-kimi-k3`, request alias `kimi-k3`, 77 local tests | implementation complete; review/CI pending |
| Adversarial reviewer | retry storm, session pinning, alias misuse, empty output, secret leakage | failure-injection and recursive redaction tests; review checklist | complete for offline gate |
| QA agent | deterministic tests, imports, compile, exact-model mock gate, no-secret output | `docs/QA_REPORT.md` | complete for offline gate |
| Remote SRE agent | Compose, private network, Secret files, watchdog, restart policy | `docker-compose.providers.yml`, `scripts/watchdog.py` | template complete; VPS unverified |
| Operator/human acceptance agent | install, live provider smoke, failover and recovery | `docs/QA_REPORT.md` | NO-GO pending credentials/VPS evidence |

## Merge and release gates

1. K3 changes merge through reviewed PRs; the current hardening merge is `3dffc85`.
2. K3 public Actions must pass on Python 3.11 and 3.13.
3. Local deterministic tests, compile/import checks and secret scan must pass.
4. DS2API account password remains inside DS2API; K3 receives only the managed
   API key or a local Secret-file binding.
5. Production activation requires exact runtime model discovery, ten synthetic
   chats, injected NVIDIA failure → DS2API failover, DS2API failure → next
   provider, and VPS restart/checkpoint evidence.

The final gate is intentionally explicit: offline CI success is not evidence of
live account access or VPS deployment.
