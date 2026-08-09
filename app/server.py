from __future__ import annotations

import json
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .config import settings
from .manager import SessionManager
from .models import (
    ApprovalResolution,
    ChatCompletionRequest,
    ConsensusRequest,
    EventType,
    OrchestrationMode,
    OrchestrationRequest,
    SubagentRequest,
)
from .prompting import flatten_openai_messages
from .security import redact_payload, redact_text, verify_bearer

settings.prepare()
manager = SessionManager(settings)


class ProviderRefreshRequest(BaseModel):
    alias: str | None = None


class ProviderRouteRequest(BaseModel):
    role: str = "orchestrator"
    preferred_models: list[str] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.gateway_api_key.strip() and settings.gateway_host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("GATEWAY_API_KEY is required when binding beyond loopback")
    try:
        yield
    finally:
        await manager.close()


app = FastAPI(
    title="Multi-Model Coding Orchestrator Gateway",
    version=__version__,
    description=(
        "Official Kimi Code ACP harness with Kimi K3, NVIDIA NIM DeepSeek/GLM, "
        "official API fallbacks, subagent routing, approvals, and audit controls."
    ),
    lifespan=lifespan,
)


def require_key(authorization: str | None = Header(default=None)) -> None:
    if not verify_bearer(authorization, settings.gateway_api_key.strip()):
        raise HTTPException(status_code=401, detail="Invalid gateway API key")


def require_internal_key(authorization: str | None = Header(default=None)) -> None:
    if not verify_bearer(authorization, settings.mcp_internal_api_key.strip()):
        raise HTTPException(status_code=401, detail="Invalid internal MCP key")


@app.get("/health")
async def health(_: None = Depends(require_key)) -> dict[str, Any]:
    available = [row for row in manager.registry.status() if row["available"]]
    return {
        "status": "ok",
        "version": __version__,
        "kimi_command": shutil.which(settings.kimi_command),
        "kimi_code_home": str(settings.kimi_code_home.resolve()),
        "live_sessions": len(manager.runtimes),
        "available_providers": [row["alias"] for row in available],
        "web_advisory_fallback": settings.enable_web_advisory_fallback,
        "self_mcp": settings.enable_self_mcp,
    }


@app.get("/healthz", include_in_schema=False)
async def healthz(_: None = Depends(require_key)) -> dict[str, Any]:
    """DS2API-compatible health endpoint; authentication remains gateway-local."""
    return await health(None)


@app.get("/ready")
async def ready(_: None = Depends(require_key)) -> JSONResponse:
    ready_profiles = manager.registry.candidates(settings.default_role)
    kimi_command = shutil.which(settings.kimi_command)
    payload = {
        "status": "ready" if ready_profiles and kimi_command else "not_ready",
        "kimi_command": kimi_command,
        "available_providers": [profile.alias for profile in ready_profiles],
    }
    return JSONResponse(status_code=200 if payload["status"] == "ready" else 503, content=payload)


@app.get("/readyz", include_in_schema=False)
async def readyz(_: None = Depends(require_key)) -> JSONResponse:
    """DS2API-compatible readiness endpoint; authentication remains gateway-local."""
    return await ready(None)


@app.get("/v1/models")
async def models(_: None = Depends(require_key)) -> dict[str, Any]:
    created = int(time.time())
    data: list[dict[str, Any]] = []
    for profile in manager.registry.profiles.values():
        row = {
            "id": profile.alias,
            "object": "model",
            "created": created,
            "owned_by": profile.transport,
            "available": profile.available(),
            "runtime_model": profile.model,
            "roles": profile.roles,
        }
        data.append(row)
        for request_alias in profile.request_aliases:
            data.append({**row, "id": request_alias, "compatibility_alias": True})
    data.insert(
        0,
        {
            "id": "multi-agent-orchestrator",
            "object": "model",
            "created": created,
            "owned_by": "local-gateway",
            "available": True,
            "roles": ["orchestrator"],
        },
    )
    return {"object": "list", "data": data}


@app.get("/api/providers")
async def providers(_: None = Depends(require_key)) -> list[dict[str, Any]]:
    return manager.registry.status()


@app.get("/api/routes")
async def routes(_: None = Depends(require_key)) -> dict[str, list[str]]:
    return manager.registry.routes


def _provider_catalog() -> list[dict[str, Any]]:
    return [
        {
            "alias": profile.alias,
            "display_name": profile.display_name,
            "transport": profile.transport,
            "provider_type": profile.provider_type,
            "model": profile.model,
            "request_aliases": profile.request_aliases,
            "base_url": profile.public_base_url(),
            "auth_required": profile.auth_required,
            "runtime_required": profile.runtime_required,
            "runtime_verified": profile.runtime_verified,
            "enabled": profile.enabled,
            "roles": profile.roles,
            "capabilities": profile.capabilities,
            "max_context_size": profile.max_context_size,
            "max_concurrency": profile.max_concurrency,
            "description": profile.description,
        }
        for profile in manager.registry.profiles.values()
    ]


def _provider_route(request: ProviderRouteRequest) -> dict[str, Any]:
    candidates = manager.registry.candidates(request.role, request.preferred_models or None)
    return {
        "role": request.role,
        "preferred_models": request.preferred_models,
        "candidates": [
            {"alias": profile.alias, "model": profile.model, "transport": profile.transport}
            for profile in candidates
        ],
    }


@app.get("/api/provider-catalog")
async def provider_catalog(_: None = Depends(require_key)) -> list[dict[str, Any]]:
    return _provider_catalog()


@app.get("/api/provider-health")
async def provider_health(_: None = Depends(require_key)) -> list[dict[str, Any]]:
    return manager.registry.status()


@app.post("/api/provider-refresh")
async def provider_refresh(request: ProviderRefreshRequest, _: None = Depends(require_key)) -> dict[str, Any]:
    if request.alias:
        try:
            manager.registry.get(request.alias)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown provider alias: {request.alias}") from exc
    manager.registry.refresh(request.alias)
    aliases = [request.alias] if request.alias else [
        profile.alias
        for profile in manager.registry.profiles.values()
        if profile.runtime_required or profile.transport == "oauth"
    ]
    results = [await manager.registry.verify_runtime(alias) for alias in aliases]
    return {"results": results, "health": manager.registry.status()}


@app.post("/api/provider-route")
async def provider_route(request: ProviderRouteRequest, _: None = Depends(require_key)) -> dict[str, Any]:
    return _provider_route(request)


@app.post("/api/orchestrations")
async def orchestrate(
    request: OrchestrationRequest,
    _: None = Depends(require_key),
) -> dict[str, Any]:
    try:
        result = await manager.run(request)
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=redact_text(str(exc))) from exc


@app.post("/api/orchestrations/stream")
async def orchestrate_stream(
    request: OrchestrationRequest,
    _: None = Depends(require_key),
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for event in manager.stream(request):
            payload = redact_payload(event.model_dump())
            yield f"event: {event.event_type.value}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/subagents/dispatch")
async def dispatch_subagent(
    request: SubagentRequest,
    _: None = Depends(require_key),
) -> dict[str, Any]:
    try:
        result = await manager.dispatch_subagent(request)
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=redact_text(str(exc))) from exc


@app.post("/api/subagents/consensus")
async def consensus(
    request: ConsensusRequest,
    _: None = Depends(require_key),
) -> dict[str, Any]:
    try:
        result = await manager.consensus(request)
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=redact_text(str(exc))) from exc


@app.get("/internal/providers")
async def internal_providers(_: None = Depends(require_internal_key)) -> list[dict[str, Any]]:
    return manager.registry.status()


@app.get("/internal/provider-catalog")
async def internal_provider_catalog(_: None = Depends(require_internal_key)) -> list[dict[str, Any]]:
    return _provider_catalog()


@app.get("/internal/provider-health")
async def internal_provider_health(_: None = Depends(require_internal_key)) -> list[dict[str, Any]]:
    return manager.registry.status()


@app.post("/internal/provider-refresh")
async def internal_provider_refresh(
    request: ProviderRefreshRequest,
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    if request.alias:
        try:
            manager.registry.get(request.alias)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown provider alias: {request.alias}") from exc
    manager.registry.refresh(request.alias)
    aliases = [request.alias] if request.alias else [
        profile.alias
        for profile in manager.registry.profiles.values()
        if profile.runtime_required or profile.transport == "oauth"
    ]
    results = [await manager.registry.verify_runtime(alias) for alias in aliases]
    return {"results": results, "health": manager.registry.status()}


@app.post("/internal/provider-route")
async def internal_provider_route(
    request: ProviderRouteRequest,
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    return _provider_route(request)


@app.post("/internal/subagents/dispatch")
async def internal_dispatch_subagent(
    request: SubagentRequest,
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    if request.mode not in {OrchestrationMode.plan, OrchestrationMode.review}:
        raise HTTPException(status_code=403, detail="Internal subagents are read-only")
    request.mode = OrchestrationMode.plan if request.role in {"planner", "researcher", "architect"} else OrchestrationMode.review
    try:
        return (await manager.dispatch_subagent(request)).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=redact_text(str(exc))) from exc


@app.post("/internal/subagents/consensus")
async def internal_consensus(
    request: ConsensusRequest,
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    request.mode = OrchestrationMode.review
    try:
        return (await manager.consensus(request)).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=redact_text(str(exc))) from exc


@app.get("/api/approvals")
async def approvals(_: None = Depends(require_key)) -> list[dict[str, Any]]:
    return await manager.approvals()


@app.post("/api/approvals/{approval_id}")
async def resolve_approval(
    approval_id: str,
    resolution: ApprovalResolution,
    _: None = Depends(require_key),
) -> dict[str, Any]:
    found = await manager.resolve_approval(
        approval_id,
        approve=resolution.approve,
        always=resolution.always,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Approval not found or already resolved")
    return {"status": "resolved"}


@app.get("/api/sessions")
async def sessions(_: None = Depends(require_key)) -> list[dict[str, Any]]:
    return manager.sessions()


@app.delete("/api/sessions/{session_id}")
async def close_session(
    session_id: str,
    forget: bool = False,
    _: None = Depends(require_key),
) -> dict[str, Any]:
    if not await manager.close_session(session_id, forget=forget):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed", "forgotten": forget}


@app.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str, _: None = Depends(require_key)) -> dict[str, Any]:
    if not await manager.cancel(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "cancelled"}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    _: None = Depends(require_key),
):
    metadata = request.metadata or {}
    mode_value = str(metadata.get("mode", "plan"))
    try:
        mode = OrchestrationMode(mode_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported orchestration mode: {mode_value}") from exc
    allowed_reasoning_efforts = {"low", "high", "max"}
    for field_name in ("reasoning_effort", "thinking"):
        value = metadata.get(field_name)
        if value is not None and (not isinstance(value, str) or value not in allowed_reasoning_efforts):
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} must be one of: low, high, max",
            )
    system, prompt = flatten_openai_messages([message.model_dump() for message in request.messages])
    model = None if request.model == "multi-agent-orchestrator" else request.model
    orchestration = OrchestrationRequest(
        prompt=prompt,
        system=system,
        mode=mode,
        model=model,
        role=str(metadata.get("role", "orchestrator")),
        cwd=metadata.get("cwd"),
        session_id=metadata.get("session_id"),
        # Preserve the standard K3/OpenAI-facing spelling while retaining
        # compatibility with the existing gateway metadata contract.
        thinking=(
            request.reasoning_effort
            or metadata.get("reasoning_effort")
            or metadata.get("thinking")
        ),
        additional_directories=metadata.get("additional_directories", []),
        mcp_servers=metadata.get("mcp_servers", []),
        allow_fallback=bool(metadata.get("allow_fallback", True)),
        preferred_models=metadata.get("preferred_models", []),
        enable_self_mcp=metadata.get("enable_self_mcp"),
    )
    completion_id = f"chatcmpl-orch-{uuid.uuid4().hex}"
    created = int(time.time())

    if not request.stream:
        try:
            result = await manager.run(orchestration)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=redact_text(str(exc))) from exc
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": result.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result.text,
                        **({"reasoning_content": result.reasoning_content} if result.reasoning_content else {}),
                        **({"tool_calls": result.tool_calls} if result.tool_calls else {}),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": result.usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "session_id": result.session_id,
            "provider": result.provider,
            "upstream_model": result.upstream_model,
            "attempts": result.attempts,
        }

    async def stream_events() -> AsyncIterator[str]:
        emitted_text = False
        emitted_reasoning = False
        emitted_tool_calls = False
        async for event in manager.stream(orchestration):
            event_payload = redact_payload(event.payload)
            if event.event_type is EventType.message:
                content = event_payload.get("content", {})
                if isinstance(content, dict) and content.get("type") == "text":
                    delta = str(content.get("text", ""))
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                    }
                    if delta:
                        emitted_text = True
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif event.event_type is EventType.thought:
                content = event_payload.get("content", {})
                if isinstance(content, dict) and content.get("type") == "text":
                    delta = str(content.get("text", ""))
                    if delta:
                        emitted_reasoning = True
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "choices": [{"index": 0, "delta": {"reasoning_content": delta}, "finish_reason": None}],
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif event.event_type is EventType.tool:
                emitted_tool_calls = bool(
                    event_payload.get("tool_call_id")
                    or event_payload.get("toolCallId")
                    or event_payload.get("title")
                    or event_payload.get("kind")
                    or event_payload.get("raw_input")
                    or event_payload.get("rawInput")
                ) or emitted_tool_calls
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"tool_calls": [event_payload]}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif event.event_type is EventType.status and event_payload.get("state") == "completed":
                final_text = str(event_payload.get("text", ""))
                if final_text and not emitted_text:
                    content_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": event_payload.get("provider", request.model),
                        "choices": [{"index": 0, "delta": {"content": final_text}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n"
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": event_payload.get("provider", request.model),
                    "choices": [{
                        "index": 0,
                        "delta": {
                            **(
                                {"reasoning_content": event_payload["reasoning_content"]}
                                if event_payload.get("reasoning_content") and not emitted_reasoning
                                else {}
                            ),
                            **(
                                {"tool_calls": event_payload["tool_calls"]}
                                if event_payload.get("tool_calls") and not emitted_tool_calls
                                else {}
                            ),
                        },
                        "finish_reason": "stop",
                    }],
                    "session_id": event_payload.get("session_id"),
                    "upstream_model": event_payload.get("upstream_model"),
                    "attempts": event_payload.get("attempts", []),
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            elif event.event_type is EventType.error:
                yield f"data: {json.dumps({'error': event_payload}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

    return StreamingResponse(stream_events(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run("app.server:app", host=settings.gateway_host, port=settings.gateway_port)
