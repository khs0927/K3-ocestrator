# Architecture

## Runtime layers

```text
Client layer
  Minis / Codex / OpenAI-compatible clients / MCP clients
                         │
Gateway layer            ▼
  REST + SSE + MCP
  session invariants / role router / circuit breaker / approvals / audit
                         │
Coding-agent layer       ▼ ACP JSON-RPC over stdio
  Official Kimi Code
  same file, terminal, MCP and permission semantics for every model
                         │
Model/provider layer     ▼
  Kimi OAuth | NVIDIA NIM | DeepSeek API | Z.AI API
```

## Core decision

Kimi Code is the common coding-agent harness. API-backed DeepSeek and GLM are not called as plain chat completion workers; the gateway starts Kimi Code with an in-memory `KIMI_MODEL_*` provider definition, then controls it through ACP. This keeps model routing separate from tool execution policy.

## Writer ownership

The default architecture uses one writer:

- Main Kimi orchestrator: may edit and execute after approval.
- Built-in Kimi subagents: allowed and governed by the main runtime.
- External DeepSeek/GLM subagents: read-only plan/review by default; return evidence and proposed patches.

This avoids concurrent edits, overlapping terminal commands and approval deadlocks. A future worktree executor may grant isolated write access per subagent and merge only validated commits.

## Provider failure handling

Each provider has:

- maximum concurrency
- minimum request interval
- consecutive failure count
- temporary circuit-open deadline
- role assignment and ordered fallback

Authentication errors open a long circuit. 429/503/capacity errors immediately open a short circuit and move the request to the next provider. Existing persistent sessions do not change providers mid-session.

## Self-MCP loop

The main orchestrator session receives this gateway as an MCP server. It can call independent DeepSeek/GLM/Kimi workers without giving those workers direct mutation ownership. Recursive self-MCP is disabled in dispatched subagent sessions.

## Browser advisory boundary

The optional Playwright bridge controls only the user's own logged-in web pages. It sends prompts and reads rendered answers. It never exports cookies, bypasses login challenges, rotates accounts, or exposes local tools. Web profiles are advisory-only and cannot run `execute` or `yolo`.

## Future isolation executor

```text
orchestrator plan
   ├─ create git worktree A → coding worker A → tests → commit
   ├─ create git worktree B → coding worker B → tests → commit
   └─ adversarial reviewers → main orchestrator selects/cherry-picks
```

This is the safe path for allowing multiple writing subagents later.
