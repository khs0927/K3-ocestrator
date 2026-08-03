# Orchestration Contract

The K3 main agent is the command authority. It combines two delegation layers:

1. Kimi Code built-in/custom subagents (`explore`, `plan`, `coder`, project specialists).
2. The local MCP gateway, which starts isolated Kimi Code ACP sessions backed by Kimi, NVIDIA DeepSeek, NVIDIA GLM, official DeepSeek or Z.AI.

A resumed session is pinned to one workspace, provider, runtime model and thinking effort. Fallback creates a fresh session and never changes a live session mid-turn. External-model subagents run in plan/review mode and cannot mutate the main workspace through the internal MCP interface.

## Required development gates

- Explore and plan before repository-wide edits.
- Parallelize independent architecture, provider, security and test reviews.
- Human approval for writes and non-read-only commands.
- Path-scoped one-time file grants.
- Tests and adversarial review before completion.
- No merge, deployment, publication or secret mutation without explicit approval.
