from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import (
    ChatCompletionRequest,
    ChatMessage,
    EventType,
    GatewayEvent,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
)


@pytest.mark.asyncio
async def test_openai_chat_error_redacts_provider_credentials(monkeypatch):
    import app.server as server

    async def fail(_request):
        raise RuntimeError("Authorization: Bearer server-secret-token")

    monkeypatch.setattr(server.manager, "run", fail)
    request = ChatCompletionRequest(messages=[ChatMessage(role="user", content="test")])

    with pytest.raises(HTTPException) as raised:
        await server.chat_completions(request, None)

    assert raised.value.status_code == 502
    assert "server-secret-token" not in str(raised.value.detail)
    assert "[REDACTED]" in str(raised.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoning_effort", ["low", "high", "max"])
async def test_openai_reasoning_effort_reaches_k3_runtime(monkeypatch, reasoning_effort):
    import app.server as server

    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return OrchestrationResult(
            session_id="session",
            text="ok",
            stop_reason="end_turn",
            mode=OrchestrationMode.plan,
            model="kimi-k3-api",
            provider="kimi-k3-api",
            role="orchestrator",
            upstream_model="kimi-k3",
        )

    monkeypatch.setattr(server.manager, "run", fake_run)
    response = await server.chat_completions(
        ChatCompletionRequest(
            model="kimi-k3-api",
            messages=[ChatMessage(role="user", content="test")],
            reasoning_effort=reasoning_effort,
        ),
        None,
    )

    assert captured["request"].thinking == reasoning_effort
    assert response["upstream_model"] == "kimi-k3"


@pytest.mark.asyncio
async def test_openai_metadata_reasoning_effort_rejects_unknown_value():
    import app.server as server

    with pytest.raises(HTTPException) as raised:
        await server.chat_completions(
            ChatCompletionRequest(
                model="kimi-k3-api",
                messages=[ChatMessage(role="user", content="test")],
                metadata={"reasoning_effort": "on"},
            ),
            None,
        )

    assert raised.value.status_code == 400


@pytest.mark.asyncio
async def test_openai_metadata_thinking_rejects_unknown_value():
    import app.server as server

    with pytest.raises(HTTPException) as raised:
        await server.chat_completions(
            ChatCompletionRequest(
                model="kimi-k3-api",
                messages=[ChatMessage(role="user", content="test")],
                metadata={"thinking": "on"},
            ),
            None,
        )

    assert raised.value.status_code == 400


@pytest.mark.asyncio
async def test_openai_non_stream_preserves_reasoning_and_tool_calls(monkeypatch):
    import app.server as server

    async def fake_run(_request):
        return OrchestrationResult(
            session_id="session",
            text="answer",
            stop_reason="end_turn",
            mode=OrchestrationMode.plan,
            model="kimi-k3-api",
            provider="kimi-k3-api",
            role="orchestrator",
            upstream_model="kimi-k3",
            reasoning_content="think first",
            tool_calls=[{"tool_call_id": "call-1", "title": "read"}],
        )

    monkeypatch.setattr(server.manager, "run", fake_run)
    response = await server.chat_completions(
        ChatCompletionRequest(
            model="kimi-k3-api",
            messages=[ChatMessage(role="user", content="test")],
            reasoning_effort="high",
        ),
        None,
    )

    message = response["choices"][0]["message"]
    assert message["content"] == "answer"
    assert message["reasoning_content"] == "think first"
    assert message["tool_calls"] == [{"tool_call_id": "call-1", "title": "read"}]


@pytest.mark.asyncio
async def test_openai_stream_preserves_reasoning_and_tool_calls_without_duplicates(monkeypatch):
    import app.server as server

    async def fake_stream(_request):
        yield GatewayEvent(
            event_type=EventType.thought,
            timestamp=0,
            payload={"content": {"type": "text", "text": "think first"}},
        )
        yield GatewayEvent(
            event_type=EventType.tool,
            timestamp=0,
            payload={"tool_call_id": "call-1", "title": "read"},
        )
        yield GatewayEvent(
            event_type=EventType.status,
            timestamp=0,
            payload={
                "state": "completed",
                "text": "answer",
                "reasoning_content": "think first",
                "tool_calls": [{"tool_call_id": "call-1", "title": "read"}],
                "provider": "kimi-k3-api",
                "upstream_model": "kimi-k3",
                "session_id": "session",
                "attempts": [],
            },
        )

    monkeypatch.setattr(server.manager, "stream", fake_stream)
    response = await server.chat_completions(
        ChatCompletionRequest(
            model="kimi-k3-api",
            messages=[ChatMessage(role="user", content="test")],
            stream=True,
        ),
        None,
    )
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    assert body.count('"reasoning_content": "think first"') == 1
    assert body.count('"tool_call_id": "call-1"') == 1
    assert '"content": "answer"' in body
    assert body.endswith("data: [DONE]\n\n")


@pytest.mark.asyncio
async def test_gateway_ready_is_not_ready_without_kimi_or_available_provider(monkeypatch):
    import app.server as server

    monkeypatch.setattr(server.manager.registry, "candidates", lambda _role: [])
    monkeypatch.setattr(server.shutil, "which", lambda _command: None)
    response = await server.ready(None)

    assert response.status_code == 503
    assert response.body is not None and b"not_ready" in response.body


@pytest.mark.asyncio
async def test_orchestration_stream_redacts_structured_secret_payload(monkeypatch):
    import app.server as server

    async def fake_stream(_request):
        yield GatewayEvent(
            event_type=EventType.message,
            timestamp=0,
            payload={"content": {"type": "text", "text": "ok"}, "api_key": "raw-stream-key"},
        )

    monkeypatch.setattr(server.manager, "stream", fake_stream)
    response = await server.orchestrate_stream(OrchestrationRequest(prompt="test"), None)
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    assert "raw-stream-key" not in body
    assert "[REDACTED]" in body
