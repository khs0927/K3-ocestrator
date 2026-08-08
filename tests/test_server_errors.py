from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import ChatCompletionRequest, ChatMessage, EventType, GatewayEvent, OrchestrationRequest


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
