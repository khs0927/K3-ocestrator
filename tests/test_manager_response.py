from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.manager import SessionManager
from app.models import OrchestrationMode, OrchestrationRequest
from app.providers import ProviderProfile


class _FakeRuntime:
    def __init__(self) -> None:
        self.answer_parts = ["streamed fallback"]
        self.thought_parts = []
        self.events = []
        self.tool_calls = {}

    async def prompt(self, _prompt: str):
        return "final answer", "max_tokens", {"total_tokens": 42}


@pytest.mark.asyncio
async def test_run_profile_preserves_acp_prompt_metadata(tmp_path):
    manager = object.__new__(SessionManager)
    manager.registry = SimpleNamespace(record_success=lambda _alias: None)
    manager.session_meta = {"session": {"updated_at": 0}}
    manager._save_state = lambda: None
    manager._provider_locks = {"test": __import__("asyncio").Semaphore(1)}
    manager._respect_min_interval = lambda _profile: _completed()
    manager._get_or_create_runtime = lambda *_args, **_kwargs: _completed(_FakeRuntime())

    request = OrchestrationRequest(
        prompt="test",
        cwd=str(tmp_path),
        mode=OrchestrationMode.review,
        role="reviewer",
        allow_fallback=False,
    )
    profile = ProviderProfile(
        alias="test",
        display_name="Test",
        transport="api",
        provider_type="openai",
        model="test-model",
        roles=["reviewer"],
    )

    result = await manager._run_profile(request, profile, "task", "session")

    assert result.text == "final answer"
    assert result.stop_reason == "max_tokens"
    assert result.usage == {"total_tokens": 42}


async def _completed(value=None):
    return value
