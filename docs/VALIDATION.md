# Validation status

Version: 0.6.0

## Completed in the build environment

- Python source compilation: passed
- Unit tests: 18 passed
- plan/review/execute/yolo policy tests: passed
- workspace path-boundary and symlink-resolution tests: passed
- prompt and persistent-session invariant tests: passed
- API-provider child-process environment isolation tests: passed
- provider availability, routing, rate-limit fallback, and circuit-breaker tests: passed
- command chaining and dangerous Git option rejection tests: passed
- one-time path-scoped file-write approval tests: passed
- browser profile and exact-origin validation tests: passed
- FastAPI gateway and optional browser server imports: passed in the build environment
- MCP server implementation checked against the stable FastMCP stdio API
- ACP runtime implementation checked against the stable 0.11.x client API and official Kimi Code ACP contract

## Dependency verification

- `agent-client-protocol>=0.11,<0.12`: stable PyPI line used for production; unreleased repository changes are not consumed
- `mcp>=1.27,<2`: official MCP Python SDK v1 production line; MCP v2 pre-releases are intentionally excluded
- `fastapi>=0.116,<1`: compatible with current 0.x releases while avoiding an unreviewed major-version transition

Context7 was used to verify the current FastMCP construction, `@mcp.tool()` registration, and `mcp.run()` stdio pattern. Official PyPI/GitHub metadata was used as the source of truth for exact release ranges.

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

Run `scripts/doctor.*`, then one role-specific `plan` or `review` request per configured provider before enabling `execute`. Keep `yolo` disabled until the disposable-container validation gate passes.
