from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import ChatCompletionRequest, ChatMessage


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
