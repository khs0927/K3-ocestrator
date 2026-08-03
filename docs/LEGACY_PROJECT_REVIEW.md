# Legacy reverse-proxy project review

## Decision

Do not base the primary orchestrator on `Kimi-Free-API`, `Chat2API`, or similar web-session reverse proxies.

## Useful ideas retained

- OpenAI-compatible request/response shape
- streaming response conversion
- browser/account-session reuse as an emergency fallback
- optional web search and long-document modes

## Reasons not to fork as the core

- private web endpoints and cookies may change without compatibility guarantees
- account/session tokens become application secrets
- the inspected project warns that an earlier upstream contained malicious injected code
- the project itself warns that reverse APIs are unstable and may create account-ban risk
- web chat does not provide ACP's structured permission, session, tool-call, cancellation, and MCP lifecycle

## Allowed role

The prior browser bridge may be enabled only for `plan` and `review` when official Kimi Code is unavailable. It must never receive code-execution authority, GitHub write credentials, shell access, or unattended multi-account rotation.
