# Upstream strategy

## Phase 1 — Sidecar integration

Use the official `kimi-code` release unchanged. Connect through `kimi acp`, install the local policy plugin, and expose the gateway to Minis.

## Phase 2 — Compatibility CI

Test every selected Kimi Code release for:

- ACP initialize/new/load/resume/prompt/cancel
- model option discovery (`k3-256k`, `k3`)
- file read/write reverse RPC
- permission request handling
- MCP server forwarding
- session recovery after process restart

Pin a known-good version in production and upgrade only after the matrix passes.

## Phase 2.5 — Native server adapter evaluation

Kimi Code now publishes a local REST/WebSocket server and OpenAPI/AsyncAPI documents. Compare it against ACP for session recovery, permission events, cancellation, MCP forwarding, and streaming. Add a second runtime adapter only when those contracts are stable enough; do not replace ACP merely to avoid the stdio subprocess.

## Phase 3 — Upstream contributions

Open focused upstream PRs for missing protocol capabilities, preferably:

- `session/close`
- richer tool-call metadata
- terminal reverse-RPC support or clearer policy hooks
- stable headless REST/WS client contract

Avoid carrying authentication, model, or protocol forks locally.

## Phase 4 — Optional managed fork

Create a fork only when a critical feature remains rejected or blocked upstream. Keep patches as a small rebased stack and never merge third-party reverse-engineered credential code into the official runtime.
