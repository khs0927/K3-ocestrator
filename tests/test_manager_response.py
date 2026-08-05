from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.manager import SessionManager
from app.models import OrchestrationMode, OrchestrationRequest, OrchestrationResult
from app.providers import ProviderProfile, ProviderRegistry
from app.acp_runtime import KimiRuntimeError


class _FakeRuntime:
    def __init__(self) -> None:
        self.answer_parts = ["streamed fallback"]
        self.thought_parts = ["internal reasoning"]
        self.events = []
        self.tool_calls = {"call-1": {"tool_call_id": "call-1", "title": "read"}}

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
    assert result.reasoning_content == "internal reasoning"
    assert result.tool_calls == [{"tool_call_id": "call-1", "title": "read"}]


@pytest.mark.asyncio
async def test_run_limits_total_attempts_and_retries_one_rate_limit(tmp_path):
    manager = object.__new__(SessionManager)
    manager.settings = SimpleNamespace(max_route_attempts=3)
    manager.registry = ProviderRegistry.load()
    profiles = [
        ProviderProfile(alias="first", display_name="First", transport="oauth", provider_type="kimi", model="first"),
        ProviderProfile(alias="second", display_name="Second", transport="oauth", provider_type="kimi", model="second"),
        ProviderProfile(alias="third", display_name="Third", transport="oauth", provider_type="kimi", model="third"),
    ]
    manager.registry.profiles.update({profile.alias: profile for profile in profiles})
    manager.registry.states.update({profile.alias: manager.registry.states["k3-256k"] for profile in profiles})
    manager.registry.retry_after_seconds = lambda _error: 0.0
    manager._candidate_profiles = lambda _request: profiles
    manager.audit = SimpleNamespace(write=lambda *args, **kwargs: None)
    manager.runtimes = {}
    manager.session_meta = {}
    manager._save_state = lambda: None
    calls: list[str] = []
    first_attempts = 0

    async def fake_run(_request, profile, _task_prompt, _external_id):
        nonlocal first_attempts
        calls.append(profile.alias)
        if profile.alias == "first":
            first_attempts += 1
            if first_attempts == 1:
                raise KimiRuntimeError("429 rate limit Retry-After: 0")
            raise KimiRuntimeError("503 overloaded")
        return OrchestrationResult(
            session_id="session",
            text="ok",
            stop_reason="end_turn",
            mode=OrchestrationMode.review,
            model=profile.alias,
            provider=profile.alias,
            role="coder",
        )

    manager._run_profile = fake_run
    request = OrchestrationRequest(
        prompt="test",
        cwd=str(tmp_path),
        mode=OrchestrationMode.review,
        role="coder",
        allow_fallback=True,
    )

    result = await manager.run(request)

    assert result.provider == "second"
    assert calls == ["first", "first", "second"]
    assert len(result.attempts) == 3


async def _completed(value=None):
    return value
