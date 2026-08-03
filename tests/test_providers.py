from __future__ import annotations

import os
import time
from pathlib import Path

from app.config import Settings
from app.manager import SessionManager
from app.providers import ProviderRegistry


def test_nvidia_profiles_become_available_with_bound_key():
    registry = ProviderRegistry.load()
    for profile in registry.profiles.values():
        if profile.api_key_env == "NVIDIA_API_KEY":
            profile.bind_api_key("nv-test")
    aliases = {profile.alias for profile in registry.available_profiles()}
    assert "nvidia-deepseek-v4-flash" in aliases
    assert "nvidia-glm-5.2" in aliases


def test_api_profiles_are_unavailable_without_keys(monkeypatch):
    for name in ("NVIDIA_API_KEY", "DEEPSEEK_API_KEY", "ZAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    aliases = {profile.alias for profile in ProviderRegistry.load().available_profiles()}
    assert aliases == {"k3-256k", "k3"}


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
    registry.get("nvidia-glm-5.2").bind_api_key("nv-test")
    registry.record_failure("nvidia-glm-5.2", "429 rate limit")
    assert registry.states["nvidia-glm-5.2"].open_until > time.time()
    assert "nvidia-glm-5.2" not in {p.alias for p in registry.candidates("planner")}


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
    assert manager.registry.get("nvidia-glm-5.2").available()
