# Compatibility policy

## Production baseline

- Kimi Code: official release exposing `kimi login`, `kimi acp`, third-party providers, project agents, sub-agents, and `KIMI_MODEL_*` temporary model definitions
- ACP Python SDK: `agent-client-protocol>=0.11,<0.12` (latest stable PyPI line at validation time)
- MCP Python SDK: `mcp>=1.27,<2` (stable v1 production line; v2 remains pre-release)
- FastAPI: `>=0.116,<1`
- Python: 3.11–3.14; CI exercises 3.11 and 3.13

The MCP implementation uses the stable FastMCP interface:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("multi-model-orchestrator")

@mcp.tool()
async def tool_name(...) -> str:
    ...

if __name__ == "__main__":
    mcp.run()  # stdio by default
```

Context7 documentation for the MCP Python SDK confirms this FastMCP/stdin-stdout pattern. Package release numbers are verified separately against the official PyPI and GitHub release metadata because documentation indexes may trail the latest maintenance release.

## Release gate

Before upgrading Kimi Code, ACP, MCP, or FastAPI, verify:

1. OAuth login is reused under `KIMI_CODE_HOME`.
2. ACP `initialize`, new/load session, prompt, permission, update, and cancel flows succeed.
3. K3 model option IDs contain `k3-256k` and `k3` or their documented successors.
4. Thinking configuration accepts the selected effort values.
5. Tool approval requests contain stable option IDs and mutation metadata.
6. A session can be closed and resumed after gateway restart.
7. NVIDIA/DeepSeek/Z.AI OpenAI- or Anthropic-compatible temporary providers initialize through Kimi Code.
8. MCP FastMCP stdio forwarding still works.
9. Plan and review modes cannot edit files or execute unsafe commands.
10. A 429/503 opens the provider circuit for new requests without switching an existing session mid-turn.
11. Browser advisory fallbacks remain read-only and reject non-allowlisted origins.
12. CI passes on every supported Python version before release.

Production should pin a known-good Kimi Code release rather than auto-upgrading without this gate.
