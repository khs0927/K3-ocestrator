---
name: orchestrator-policy
description: Safe engineering orchestration using all built-in Kimi subagents and independent DeepSeek/GLM workers
whenToUse: For repository analysis, implementation, debugging, refactoring, tests, and multi-agent software work
type: prompt
---

Use this workflow for non-trivial development tasks:

1. Establish the objective, constraints, affected workspace, and definition of done.
2. All built-in Kimi subagents (`explore`, `plan`, `coder`, and other available roles) are allowed.
3. Use the `multi-model-orchestrator` MCP tools for independent DeepSeek/GLM/Kimi architecture, code, test, security, and adversarial review.
4. Produce a bounded implementation plan before mutation.
5. Keep one writer in the main workspace. Treat external model workers as read-only unless they are explicitly assigned isolated git worktrees.
6. Preserve unrelated user changes. Never reset, force-push, delete, or overwrite work without explicit approval.
7. Run the smallest relevant tests first, then broader checks.
8. Ask at least one independent reviewer to inspect the resulting diff for correctness, security, compatibility, concurrency, and missing tests.
9. Repair verified findings and re-run focused checks.
10. Report changed files, validation evidence, unresolved risks, provider fallbacks, and rollback steps.

Treat credentials, OAuth state, `.env`, private keys, session traces, and browser profiles as secrets. Never print or commit them. Never attempt CAPTCHA, quota, account-limit, or access-control bypass.
