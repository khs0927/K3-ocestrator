from __future__ import annotations

import json

import httpx
from mcp.server.fastmcp import FastMCP

from .config import settings

mcp = FastMCP(
    "multi-model-orchestrator",
    instructions=(
        "Dispatch isolated DeepSeek, GLM and Kimi subagents for planning, architecture, research, "
        "testing and adversarial review. The main Kimi session remains responsible for mutations."
    ),
)


def _base_url() -> str:
    return f"http://{settings.gateway_host}:{settings.gateway_port}"


def _headers() -> dict[str, str]:
    key = settings.resolved_mcp_internal_api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


@mcp.tool()
async def dispatch_subagent(
    task: str,
    cwd: str,
    role: str = "reviewer",
    model: str = "",
    thinking: str = "high",
) -> str:
    """Dispatch one isolated coding subagent; use model='kimi-k3' after Kimi OAuth login for the DS2API-compatible K3 route."""
    payload = {
        "prompt": task,
        "cwd": cwd,
        "role": role,
        "mode": "plan" if role in {"planner", "researcher", "architect"} else "review",
        "model": model or None,
        "thinking": thinking,
        "allow_fallback": True,
    }
    async with httpx.AsyncClient(timeout=settings.prompt_timeout_seconds) as client:
        response = await client.post(f"{_base_url()}/internal/subagents/dispatch", headers=_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return f"Provider: {data['provider']}\nRole: {data['role']}\n\n{data['text']}"


@mcp.tool()
async def multi_model_consensus(
    task: str,
    cwd: str,
    roles: list[str] | None = None,
    synthesize: bool = True,
) -> str:
    """Run independent Kimi, DeepSeek and GLM reviewers in parallel and synthesize evidence."""
    payload = {
        "prompt": task,
        "cwd": cwd,
        "roles": roles or ["architect", "reviewer", "security", "test"],
        "mode": "review",
        "synthesize": synthesize,
    }
    async with httpx.AsyncClient(timeout=settings.prompt_timeout_seconds) as client:
        response = await client.post(f"{_base_url()}/internal/subagents/consensus", headers=_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("synthesis"):
            return data["synthesis"]["text"]
        return "\n\n".join(
            f"## {item['role']} via {item['provider']}\n{item['text']}" for item in data["responses"]
        )


@mcp.tool()
async def provider_status() -> str:
    """Return redacted provider availability and circuit-breaker status."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{_base_url()}/internal/providers", headers=_headers())
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def provider_catalog() -> str:
    """Return the redacted provider catalog without credentials."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{_base_url()}/internal/provider-catalog", headers=_headers())
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def provider_health() -> str:
    """Return provider health and circuit-breaker state."""
    return await provider_status()


@mcp.tool()
async def provider_refresh(alias: str = "") -> str:
    """Clear a provider circuit or permanently-disabled model state."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{_base_url()}/internal/provider-refresh",
            headers=_headers(),
            json={"alias": alias or None},
        )
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def provider_route(role: str = "orchestrator", preferred_models: list[str] | None = None) -> str:
    """Preview the currently available route candidates for a role."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{_base_url()}/internal/provider-route",
            headers=_headers(),
            json={"role": role, "preferred_models": preferred_models or []},
        )
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
