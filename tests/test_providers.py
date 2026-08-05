from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from app.config import Settings
from app.manager import SessionManager
from app.providers import ProviderRegistry


def test_nvidia_profiles_become_available_with_bound_key():
    registry = ProviderRegistry.load()
    for profile in registry.profiles.values():
        if profile.api_key_env == "NVIDIA_API_KEY":
            profile.bind_api_key("nv-test")
            profile.runtime_verified = True
    aliases = {profile.alias for profile in registry.available_profiles()}
    assert "nvidia-deepseek-v4-flash" in aliases
    assert "nvidia-glm-5.2" in aliases


def test_api_profiles_are_unavailable_without_keys(monkeypatch):
    for name in ("NVIDIA_API_KEY", "DEEPSEEK_API_KEY", "ZAI_API_KEY", "DS2API_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    aliases = {profile.alias for profile in ProviderRegistry.load().available_profiles()}
    assert aliases == {"k3-256k", "k3"}


def test_ds2api_is_opt_in_and_does_not_require_gateway_key():
    registry = ProviderRegistry.load()
    profile = registry.get("ds2api-deepseek-v4-flash")
    assert profile.auth_required is False
    assert profile.available() is False

    profile.enabled = True
    assert profile.available() is False
    profile.runtime_verified = True
    assert profile.available() is True
    env = profile.kimi_environment("high")
    assert env["KIMI_MODEL_NAME"] == "deepseek-v4-flash"
    assert env["KIMI_MODEL_BASE_URL"] == "http://127.0.0.1:5001/v1"
    assert "KIMI_MODEL_API_KEY" not in env


def test_deepseek_route_places_ds2api_after_nvidia():
    route = ProviderRegistry.load().routes["coder"]
    assert route.index("ds2api-deepseek-v4-flash") == route.index("nvidia-deepseek-v4-flash") + 1


def test_kimi_environment_uses_bound_secret_without_export(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    profile = ProviderRegistry.load().get("nvidia-deepseek-v4-flash")
    profile.bind_api_key("nv-test")
    env = profile.kimi_environment("high")
    assert env["KIMI_MODEL_NAME"] == "deepseek-ai/deepseek-v4-flash"
    assert env["KIMI_MODEL_PROVIDER_TYPE"] == "openai"
    assert env["KIMI_MODEL_BASE_URL"] == "https://integrate.api.nvidia.com/v1"
    assert env["KIMI_MODEL_API_KEY"] == "nv-test"
    assert "NVIDIA_API_KEY" not in os.environ


def test_rate_limit_failures_open_circuit():
    registry = ProviderRegistry.load()
    profile = registry.get("nvidia-glm-5.2")
    profile.bind_api_key("nv-test")
    profile.runtime_verified = True
    registry.record_failure("nvidia-glm-5.2", "429 rate limit")
    assert registry.states["nvidia-glm-5.2"].open_until > time.time()
    assert "nvidia-glm-5.2" not in {p.alias for p in registry.candidates("planner")}


def test_failure_classification_disables_only_missing_model_until_refresh():
    registry = ProviderRegistry.load()
    profile = registry.get("nvidia-glm-5.2")
    profile.bind_api_key("nv-test")
    profile.runtime_verified = True

    assert registry.record_failure(profile.alias, "HTTP 404 model not found") == "permanent"
    assert registry.states[profile.alias].permanently_disabled is True
    assert profile.alias not in {item.alias for item in registry.candidates("planner")}

    registry.refresh(profile.alias)
    assert registry.states[profile.alias].permanently_disabled is False
    assert profile.alias in {item.alias for item in registry.candidates("planner")}


def test_retry_after_is_bounded_and_defaults_when_missing():
    registry = ProviderRegistry.load()
    assert registry.retry_after_seconds("429 Retry-After: 2.5") == 2.5
    assert registry.retry_after_seconds("429 rate limit") == 1.0
    assert registry.retry_after_seconds("Retry-After: 999") == 30.0
    retry_at = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=5), usegmt=True)
    assert 0.0 <= registry.retry_after_seconds(f"Retry-After: {retry_at}") <= 10.0


def test_ds2api_runtime_gate_checks_health_readiness_and_exact_model(monkeypatch):
    class Response:
        status_code = 200
        is_success = True

        def __init__(self, url: str):
            self.url = url

        def raise_for_status(self):
            return None

        def json(self):
            if self.url.endswith("/models"):
                return {"data": [{"id": "deepseek-v4-flash"}]}
            return {"status": "ok"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            return Response(url)

    monkeypatch.setattr("app.providers.httpx.AsyncClient", lambda **_kwargs: Client())
    registry = ProviderRegistry.load()
    profile = registry.get("ds2api-deepseek-v4-flash")
    profile.enabled = True

    result = __import__("asyncio").run(registry.verify_runtime(profile.alias))

    assert result["verified"] is True
    assert result["checks"]["healthz"]["ok"] is True
    assert result["checks"]["readyz"]["ok"] is True
    assert profile.runtime_verified is True
    assert profile.available() is True


def test_settings_secret_is_bound_not_exported(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    settings = Settings(
        _env_file=None, nvidia_api_key="from-settings", gateway_api_key="local",
        default_workspace=tmp_path / "workspace", kimi_code_home=tmp_path / "kimi-home",
        audit_log=tmp_path / "audit.jsonl", state_file=tmp_path / "state.json",
        provider_profiles_file=tmp_path / "profiles.json", routing_file=tmp_path / "routes.json",
    )
    settings.prepare()
    manager = SessionManager(settings)
    assert "NVIDIA_API_KEY" not in os.environ
    assert manager.registry.get("nvidia-glm-5.2").api_key() == "from-settings"
    manager.registry.get("nvidia-glm-5.2").runtime_verified = True
    assert manager.registry.get("nvidia-glm-5.2").available()


def test_ds2api_secret_file_is_bound_without_environment_export(tmp_path: Path, monkeypatch):
    secret = tmp_path / "ds2api-api-key"
    secret.write_text("managed-key\n", encoding="utf-8")
    monkeypatch.delenv("DS2API_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        ds2api_enabled=True,
        ds2api_api_key_file=secret,
        default_workspace=tmp_path / "workspace",
        kimi_code_home=tmp_path / "kimi-home",
        audit_log=tmp_path / "audit.jsonl",
        state_file=tmp_path / "state.json",
        provider_profiles_file=tmp_path / "profiles.json",
        routing_file=tmp_path / "routes.json",
    )
    settings.prepare()
    manager = SessionManager(settings)
    profile = manager.registry.get("ds2api-deepseek-v4-flash")
    assert profile.api_key() == "managed-key"
    assert profile.available() is False
    assert "DS2API_API_KEY" not in os.environ
