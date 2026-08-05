# Validation status

Version: 0.6.0

## Completed in the build environment

- Python source compilation: passed
- Unit tests: 27 passed
- plan/review/execute/yolo policy tests: passed
- workspace path-boundary and symlink-resolution tests: passed
- prompt and persistent-session invariant tests: passed
- ACP prompt response text, stop reason, and usage metadata preservation test: passed
- API-provider child-process environment isolation tests: passed
- provider availability, exact runtime discovery, routing, rate-limit fallback, and circuit-breaker tests: passed
- command chaining and dangerous Git option rejection tests: passed
- one-time path-scoped file-write approval tests: passed
- browser profile and exact-origin validation tests: passed
- container sandbox manifest baseline tests: passed
- FastAPI gateway and optional browser server imports: passed in the build environment
- MCP server implementation checked against the stable FastMCP stdio API
- ACP runtime implementation checked against the stable 0.11.x client API and official Kimi Code ACP contract
- GitHub Actions passed on Python 3.11 and Python 3.13

The deterministic suite includes a mocked DS2API gate that checks `/healthz`, `/readyz`, and `/v1/models` and refuses activation when the exact model ID is absent.

## Container baseline verification

The repository now contains a non-root Kimi Code image and a restricted Docker Compose profile with a read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, loopback-only host binding, a single writable workspace mount, separate OAuth/state mounts, resource limits, and YOLO disabled. Static tests enforce these invariants.

The image has not been built in the current connector environment and no real OAuth/API request has run inside it. Host-level egress allowlisting and a disposable-repository end-to-end cycle remain operator-side release gates.

## Dependency verification

- `agent-client-protocol>=0.11,<0.12`: stable PyPI line used for production; unreleased repository changes are not consumed
- `mcp>=1.27,<2`: official MCP Python SDK v1 production line; MCP v2 pre-releases are intentionally excluded
- `fastapi>=0.116,<1`: compatible with current 0.x releases while avoiding an unreviewed major-version transition

Context7 was used to verify the current FastMCP construction, `@mcp.tool()` registration, `mcp.run()` stdio pattern, ACP subprocess spawning, session creation/resume, prompt delivery, session updates, and permission callbacks. Official package and repository metadata was used as the source of truth for exact release ranges.

## Not possible without the operator's accounts

No Kimi OAuth session or NVIDIA/DeepSeek/Z.AI credential was available in the build environment. The following therefore remain operator-side smoke tests and are not claimed as completed:

1. `kimi login` and `kimi acp` initialization with the real account
2. K3 and K3-256K real prompts
3. NVIDIA DeepSeek V4 Flash/Pro calls
4. NVIDIA GLM-5.2 call
5. DeepSeek and Z.AI official fallback calls
6. live tool permission and file-edit cycle inside a disposable repository
7. Minis end-to-end provider registration
8. browser DOM selectors after manual DeepSeek/GLM login
9. Docker image build, container OAuth login, and end-to-end execution with host egress policy

Run `scripts/doctor.*`, then one role-specific `plan` or `review` request per configured provider before enabling `execute`. Keep `yolo` disabled until the disposable-container validation gate passes.
