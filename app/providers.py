from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


ProviderTransport = Literal["oauth", "api", "web"]
ProviderProtocol = Literal["kimi", "openai", "anthropic"]


class ProviderProfile(BaseModel):
    alias: str
    display_name: str
    transport: ProviderTransport = "api"
    provider_type: ProviderProtocol = "openai"
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_value: str | None = Field(default=None, exclude=True, repr=False)
    max_context_size: int = Field(default=262_144, ge=1)
    max_output_size: int | None = Field(default=None, ge=1)
    capabilities: list[str] = Field(default_factory=lambda: ["thinking"])
    reasoning_key: str | None = None
    default_thinking: str = "high"
    roles: list[str] = Field(default_factory=list)
    priority: int = 100
    max_concurrency: int = Field(default=1, ge=1, le=32)
    min_interval_seconds: float = Field(default=0.0, ge=0)
    enabled: bool = True
    advisory_only: bool = False
    description: str = ""

    def bind_api_key(self, value: str | None) -> None:
        self.api_key_value = (value or "").strip() or None

    def api_key(self) -> str | None:
        if self.transport == "oauth":
            return None
        if self.api_key_value:
            return self.api_key_value
        if not self.api_key_env:
            return None
        value = os.getenv(self.api_key_env, "").strip()
        return value or None

    def available(self) -> bool:
        if not self.enabled:
            return False
        if self.transport == "oauth":
            return True
        if self.transport == "web":
            return bool(self.base_url)
        return bool(self.base_url and self.api_key())

    def kimi_environment(self, thinking: str | None = None) -> dict[str, str]:
        if self.transport != "api":
            return {}
        key = self.api_key()
        if not key:
            raise RuntimeError(f"Missing {self.api_key_env} for provider profile {self.alias}")
        env = {
            "KIMI_MODEL_NAME": self.model,
            "KIMI_MODEL_DISPLAY_NAME": self.display_name,
            "KIMI_MODEL_API_KEY": key,
            "KIMI_MODEL_PROVIDER_TYPE": self.provider_type,
            "KIMI_MODEL_MAX_CONTEXT_SIZE": str(self.max_context_size),
            "KIMI_MODEL_CAPABILITIES": ",".join(self.capabilities),
            "KIMI_MODEL_THINKING_EFFORT": thinking or self.default_thinking,
        }
        if self.base_url:
            env["KIMI_MODEL_BASE_URL"] = self.base_url
        if self.max_output_size:
            env["KIMI_MODEL_MAX_OUTPUT_SIZE"] = str(self.max_output_size)
        if self.reasoning_key:
            env["KIMI_MODEL_REASONING_KEY"] = self.reasoning_key
        return env


DEFAULT_PROFILES: list[dict[str, Any]] = [
    {
        "alias": "k3-256k",
        "display_name": "Kimi K3 256K OAuth",
        "transport": "oauth",
        "provider_type": "kimi",
        "model": "k3-256k",
        "max_context_size": 262144,
        "roles": ["orchestrator", "planner", "coder", "reviewer", "researcher"],
        "priority": 10,
        "max_concurrency": 4,
        "description": "Official Kimi Code OAuth-managed model; primary orchestrator.",
    },
    {
        "alias": "k3",
        "display_name": "Kimi K3 1M OAuth",
        "transport": "oauth",
        "provider_type": "kimi",
        "model": "k3",
        "max_context_size": 1048576,
        "roles": ["orchestrator", "planner", "reviewer", "researcher", "long_context"],
        "priority": 20,
        "max_concurrency": 2,
        "description": "Official Kimi Code OAuth model for very large repositories and long context.",
    },
    {
        "alias": "nvidia-deepseek-v4-flash",
        "display_name": "NVIDIA DeepSeek V4 Flash",
        "transport": "api",
        "provider_type": "openai",
        "model": "deepseek-ai/deepseek-v4-flash",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["coder", "reviewer", "fast", "test", "researcher"],
        "priority": 30,
        "max_concurrency": 1,
        "min_interval_seconds": 1.5,
        "description": "Free NVIDIA NIM prototype endpoint; fast coding worker.",
    },
    {
        "alias": "nvidia-glm-5.2",
        "display_name": "NVIDIA GLM-5.2",
        "transport": "api",
        "provider_type": "openai",
        "model": "z-ai/glm-5.2",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["planner", "architect", "reviewer", "researcher", "long_context"],
        "priority": 35,
        "max_concurrency": 1,
        "min_interval_seconds": 1.5,
        "description": "Free NVIDIA NIM prototype endpoint; architecture and long-context reviewer.",
    },
    {
        "alias": "nvidia-deepseek-v4-pro",
        "display_name": "NVIDIA DeepSeek V4 Pro",
        "transport": "api",
        "provider_type": "openai",
        "model": "deepseek-ai/deepseek-v4-pro",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["reviewer", "architect", "hard_reasoning", "security"],
        "priority": 40,
        "max_concurrency": 1,
        "min_interval_seconds": 2.0,
        "description": "Free NVIDIA NIM prototype endpoint; difficult reasoning and final review.",
    },
    {
        "alias": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash Official",
        "transport": "api",
        "provider_type": "openai",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["coder", "reviewer", "fast", "test"],
        "priority": 60,
        "max_concurrency": 2,
        "description": "Low-cost official DeepSeek fallback when NVIDIA endpoint is unavailable.",
    },
    {
        "alias": "deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro Official",
        "transport": "api",
        "provider_type": "anthropic",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key_env": "DEEPSEEK_API_KEY",
        "max_context_size": 1048576,
        "max_output_size": 131072,
        "capabilities": ["thinking"],
        "roles": ["reviewer", "architect", "hard_reasoning", "security"],
        "priority": 65,
        "max_concurrency": 1,
        "description": "Official DeepSeek Anthropic-compatible endpoint for coding-agent fallback.",
    },
    {
        "alias": "zai-glm-5.2",
        "display_name": "Z.AI GLM-5.2 API",
        "transport": "api",
        "provider_type": "openai",
        "model": "glm-5.2",
        "base_url": "https://api.z.ai/api/paas/v4",
        "api_key_env": "ZAI_API_KEY",
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["planner", "architect", "reviewer", "researcher", "long_context"],
        "priority": 70,
        "max_concurrency": 1,
        "description": "Official pay-as-you-go Z.AI API fallback; not the restricted Coding Plan quota.",
    },
    {
        "alias": "deepseek-web-advisory",
        "display_name": "DeepSeek Web Advisory",
        "transport": "web",
        "provider_type": "openai",
        "model": "deepseek-web",
        "base_url": None,
        "api_key_env": "DEEPSEEK_WEB_BRIDGE_KEY",
        "roles": ["planner", "reviewer", "researcher"],
        "priority": 200,
        "advisory_only": True,
        "description": "Optional personal browser bridge; no local tool execution.",
    },
    {
        "alias": "glm-web-advisory",
        "display_name": "GLM Web Advisory",
        "transport": "web",
        "provider_type": "openai",
        "model": "glm-web",
        "base_url": None,
        "api_key_env": "GLM_WEB_BRIDGE_KEY",
        "roles": ["planner", "reviewer", "researcher"],
        "priority": 210,
        "advisory_only": True,
        "description": "Optional personal browser bridge; no local tool execution.",
    },
]


DEFAULT_ROUTES: dict[str, list[str]] = {
    "orchestrator": ["k3-256k", "k3", "nvidia-glm-5.2", "nvidia-deepseek-v4-pro"],
    "planner": ["k3-256k", "nvidia-glm-5.2", "k3", "zai-glm-5.2", "glm-web-advisory"],
    "architect": ["nvidia-glm-5.2", "k3", "nvidia-deepseek-v4-pro", "zai-glm-5.2"],
    "coder": ["k3-256k", "nvidia-deepseek-v4-flash", "deepseek-v4-flash", "nvidia-glm-5.2"],
    "reviewer": ["nvidia-deepseek-v4-pro", "nvidia-glm-5.2", "k3-256k", "deepseek-v4-pro", "zai-glm-5.2"],
    "researcher": ["nvidia-glm-5.2", "k3", "nvidia-deepseek-v4-flash", "glm-web-advisory", "deepseek-web-advisory"],
    "fast": ["nvidia-deepseek-v4-flash", "deepseek-v4-flash", "k3-256k"],
    "test": ["nvidia-deepseek-v4-flash", "k3-256k", "deepseek-v4-flash"],
    "security": ["nvidia-deepseek-v4-pro", "k3", "deepseek-v4-pro", "nvidia-glm-5.2"],
    "long_context": ["k3", "nvidia-glm-5.2", "nvidia-deepseek-v4-pro", "zai-glm-5.2"],
    "hard_reasoning": ["k3", "nvidia-deepseek-v4-pro", "nvidia-glm-5.2", "deepseek-v4-pro"],
}


@dataclass
class ProviderRuntimeState:
    consecutive_failures: int = 0
    open_until: float = 0.0
    last_error: str | None = None
    last_success_at: float | None = None
    last_started_at: float = 0.0
    total_successes: int = 0
    total_failures: int = 0


@dataclass
class ProviderRegistry:
    profiles: dict[str, ProviderProfile]
    routes: dict[str, list[str]]
    states: dict[str, ProviderRuntimeState] = field(default_factory=dict)

    @classmethod
    def load(cls, profile_file: Path | None = None, route_file: Path | None = None) -> "ProviderRegistry":
        raw_profiles: list[dict[str, Any]] = list(DEFAULT_PROFILES)
        if profile_file and profile_file.exists():
            try:
                payload = json.loads(profile_file.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    payload = payload.get("profiles", [])
                if isinstance(payload, list):
                    by_alias = {item["alias"]: item for item in raw_profiles}
                    for item in payload:
                        if isinstance(item, dict) and item.get("alias"):
                            base = dict(by_alias.get(str(item["alias"]), {}))
                            base.update(item)
                            by_alias[str(item["alias"])] = base
                    raw_profiles = list(by_alias.values())
            except (OSError, json.JSONDecodeError, ValidationError):
                pass
        profiles = {p.alias: p for p in (ProviderProfile.model_validate(item) for item in raw_profiles)}
        routes = {key: list(value) for key, value in DEFAULT_ROUTES.items()}
        if route_file and route_file.exists():
            try:
                payload = json.loads(route_file.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        if isinstance(value, list):
                            routes[str(key)] = [str(item) for item in value]
            except (OSError, json.JSONDecodeError):
                pass
        return cls(profiles=profiles, routes=routes, states={alias: ProviderRuntimeState() for alias in profiles})

    def get(self, alias: str) -> ProviderProfile:
        try:
            return self.profiles[alias]
        except KeyError as exc:
            raise KeyError(f"Unknown model/provider alias: {alias}") from exc

    def available_profiles(self) -> list[ProviderProfile]:
        return [profile for profile in self.profiles.values() if profile.available()]

    def candidates(self, role: str, preferred: list[str] | None = None) -> list[ProviderProfile]:
        aliases = preferred or self.routes.get(role) or self.routes["orchestrator"]
        result: list[ProviderProfile] = []
        now = time.time()
        for alias in aliases:
            profile = self.profiles.get(alias)
            if not profile or not profile.available():
                continue
            state = self.states.setdefault(alias, ProviderRuntimeState())
            if state.open_until > now:
                continue
            result.append(profile)
        return result

    def record_success(self, alias: str) -> None:
        state = self.states.setdefault(alias, ProviderRuntimeState())
        state.consecutive_failures = 0
        state.open_until = 0.0
        state.last_error = None
        state.last_success_at = time.time()
        state.total_successes += 1

    def record_failure(self, alias: str, error: Exception | str) -> None:
        state = self.states.setdefault(alias, ProviderRuntimeState())
        state.consecutive_failures += 1
        state.total_failures += 1
        state.last_error = str(error)
        message = str(error).lower()
        auth_failure = any(token in message for token in ("401", "invalid api key", "authentication"))
        capacity_failure = any(token in message for token in ("429", "rate limit", "capacity", "overloaded", "503"))
        if auth_failure:
            cooldown = 900.0
        elif capacity_failure:
            cooldown = min(300.0, 20.0 * state.consecutive_failures)
        else:
            cooldown = min(120.0, 5.0 * state.consecutive_failures)
        if auth_failure or capacity_failure or state.consecutive_failures >= 2:
            state.open_until = time.time() + cooldown

    def status(self) -> list[dict[str, Any]]:
        now = time.time()
        rows: list[dict[str, Any]] = []
        for alias, profile in self.profiles.items():
            state = self.states.setdefault(alias, ProviderRuntimeState())
            rows.append(
                {
                    "alias": alias,
                    "display_name": profile.display_name,
                    "transport": profile.transport,
                    "model": profile.model,
                    "available": profile.available(),
                    "advisory_only": profile.advisory_only,
                    "roles": profile.roles,
                    "circuit_open": state.open_until > now,
                    "open_for_seconds": max(0.0, state.open_until - now),
                    "consecutive_failures": state.consecutive_failures,
                    "last_error": state.last_error,
                    "last_success_at": state.last_success_at,
                    "total_successes": state.total_successes,
                    "total_failures": state.total_failures,
                }
            )
        return rows
