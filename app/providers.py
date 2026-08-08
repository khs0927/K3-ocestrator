from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError

from .security import redact_text


ProviderTransport = Literal["oauth", "api", "web"]
ProviderProtocol = Literal["kimi", "openai", "anthropic"]


def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        value = Path(path).expanduser().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


class ProviderProfile(BaseModel):
    alias: str
    display_name: str
    transport: ProviderTransport = "api"
    provider_type: ProviderProtocol = "openai"
    provider_id: str | None = None
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_value: str | None = Field(default=None, exclude=True, repr=False)
    auth_required: bool = True
    runtime_required: bool = False
    runtime_verified: bool = False
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
        if value:
            return value
        return _read_secret_file(os.getenv(f"{self.api_key_env}_FILE", "").strip())

    def health_key(self) -> str:
        provider = self.provider_id
        if not provider and self.base_url:
            parsed = urlparse(self.base_url)
            provider = parsed.netloc or parsed.path
        provider = provider or self.transport
        return f"{provider}:{self.model}"

    def available(self) -> bool:
        if not self.enabled:
            return False
        if self.transport == "oauth":
            return True
        if self.transport == "web":
            return bool(self.base_url)
        return bool(
            self.base_url
            and (not self.auth_required or self.api_key())
            and (not self.runtime_required or self.runtime_verified)
        )

    def kimi_environment(self, thinking: str | None = None) -> dict[str, str]:
        if self.transport != "api":
            return {}
        key = self.api_key()
        if self.auth_required and not key:
            raise RuntimeError(f"Missing {self.api_key_env} for provider profile {self.alias}")
        env = {
            "KIMI_MODEL_NAME": self.model,
            "KIMI_MODEL_DISPLAY_NAME": self.display_name,
            "KIMI_MODEL_PROVIDER_TYPE": self.provider_type,
            "KIMI_MODEL_MAX_CONTEXT_SIZE": str(self.max_context_size),
            "KIMI_MODEL_CAPABILITIES": ",".join(self.capabilities),
            "KIMI_MODEL_THINKING_EFFORT": thinking or self.default_thinking,
        }
        if key:
            env["KIMI_MODEL_API_KEY"] = key
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
        "alias": "kimi-k3-api",
        "display_name": "Kimi K3 Official API",
        "transport": "api",
        "provider_type": "openai",
        "model": "kimi-k3",
        "base_url": "https://api.moonshot.ai/v1",
        "api_key_env": "KIMI_API_KEY",
        "runtime_required": True,
        "max_context_size": 1048576,
        "capabilities": ["thinking", "tool_calls"],
        "roles": ["orchestrator", "planner", "coder", "reviewer", "researcher", "long_context"],
        "priority": 25,
        "max_concurrency": 2,
        "min_interval_seconds": 1.0,
        "description": "Official OpenAI-compatible Kimi K3 API; opt-in through KIMI_API_KEY and exact model discovery.",
    },
    {
        "alias": "kimi-k3-self-hosted",
        "display_name": "Kimi K3 Self-hosted",
        "transport": "api",
        "provider_type": "openai",
        "model": "moonshotai/Kimi-K3",
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key_env": "K3_SELF_HOSTED_API_KEY",
        "auth_required": False,
        "runtime_required": True,
        "enabled": False,
        "max_context_size": 1048576,
        "capabilities": ["thinking", "tool_calls", "vision"],
        "roles": ["orchestrator", "planner", "coder", "reviewer", "researcher", "long_context"],
        "priority": 26,
        "max_concurrency": 1,
        "description": "Opt-in OpenAI-compatible vLLM/SGLang endpoint; exact moonshotai/Kimi-K3 discovery is required.",
    },
    {
        "alias": "nvidia-deepseek-v4-flash",
        "display_name": "NVIDIA DeepSeek V4 Flash",
        "transport": "api",
        "provider_type": "openai",
        "model": "deepseek-ai/deepseek-v4-flash",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "runtime_required": True,
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
        "runtime_required": True,
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["planner", "architect", "reviewer", "researcher", "long_context"],
        "priority": 35,
        "max_concurrency": 1,
        "min_interval_seconds": 1.5,
        "description": "Free NVIDIA NIM prototype endpoint; architecture and long-context reviewer.",
    },
    {
        "alias": "ds2api-deepseek-v4-flash",
        "display_name": "DS2API DeepSeek V4 Flash",
        "transport": "api",
        "provider_type": "openai",
        "provider_id": "ds2api",
        "model": "deepseek-v4-flash",
        "base_url": "http://127.0.0.1:5001/v1",
        "api_key_env": "DS2API_API_KEY",
        "auth_required": False,
        "runtime_required": True,
        "enabled": False,
        "max_context_size": 1048576,
        "capabilities": ["thinking"],
        "roles": ["coder", "reviewer", "fast", "test"],
        "priority": 50,
        "max_concurrency": 1,
        "description": "Opt-in DeepSeek web-session compatibility fallback; account/session login stays inside DS2API.",
    },
    {
        "alias": "nvidia-deepseek-v4-pro",
        "display_name": "NVIDIA DeepSeek V4 Pro",
        "transport": "api",
        "provider_type": "openai",
        "model": "deepseek-ai/deepseek-v4-pro",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "runtime_required": True,
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
        "runtime_required": True,
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
        "runtime_required": True,
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
        "runtime_required": True,
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
    "orchestrator": ["k3-256k", "k3", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-glm-5.2", "nvidia-deepseek-v4-pro"],
    "planner": ["k3-256k", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-glm-5.2", "k3", "zai-glm-5.2", "glm-web-advisory"],
    "architect": ["nvidia-glm-5.2", "k3", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-deepseek-v4-pro", "zai-glm-5.2"],
    "coder": ["k3-256k", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-deepseek-v4-flash", "ds2api-deepseek-v4-flash", "deepseek-v4-flash", "nvidia-glm-5.2"],
    "reviewer": ["nvidia-deepseek-v4-pro", "nvidia-glm-5.2", "k3-256k", "kimi-k3-api", "kimi-k3-self-hosted", "deepseek-v4-pro", "zai-glm-5.2"],
    "researcher": ["nvidia-glm-5.2", "k3", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-deepseek-v4-flash", "glm-web-advisory", "deepseek-web-advisory"],
    "fast": ["nvidia-deepseek-v4-flash", "ds2api-deepseek-v4-flash", "deepseek-v4-flash", "k3-256k"],
    "test": ["nvidia-deepseek-v4-flash", "ds2api-deepseek-v4-flash", "k3-256k", "deepseek-v4-flash"],
    "security": ["nvidia-deepseek-v4-pro", "k3", "kimi-k3-api", "kimi-k3-self-hosted", "deepseek-v4-pro", "nvidia-glm-5.2"],
    "long_context": ["k3", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-glm-5.2", "nvidia-deepseek-v4-pro", "zai-glm-5.2"],
    "hard_reasoning": ["k3", "kimi-k3-api", "kimi-k3-self-hosted", "nvidia-deepseek-v4-pro", "nvidia-glm-5.2", "deepseek-v4-pro"],
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
    permanently_disabled: bool = False


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
        for profile in profiles.values():
            if (
                profile.provider_id == "ds2api"
                or profile.alias.startswith("ds2api-")
                or (profile.base_url and urlparse(profile.base_url).netloc.endswith(":5001"))
            ) and profile.model != "deepseek-v4-flash":
                profile.enabled = False
                profile.runtime_verified = False
                profile.description = (
                    f"{profile.description} Disabled: DS2API profiles are restricted to deepseek-v4-flash."
                ).strip()
        # Runtime discovery is process-local evidence; never allow a checked-in
        # JSON file to claim that an API model was verified.
        for profile in profiles.values():
            if profile.transport == "api" and profile.runtime_required:
                profile.runtime_verified = False
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
        return cls(
            profiles=profiles,
            routes=routes,
            states={profile.health_key(): ProviderRuntimeState() for profile in profiles.values()},
        )

    def get(self, alias: str) -> ProviderProfile:
        try:
            return self.profiles[alias]
        except KeyError as exc:
            raise KeyError(f"Unknown model/provider alias: {alias}") from exc

    def available_profiles(self) -> list[ProviderProfile]:
        return [profile for profile in self.profiles.values() if profile.available()]

    def state_for(self, alias: str) -> ProviderRuntimeState:
        profile = self.get(alias)
        return self.states.setdefault(profile.health_key(), ProviderRuntimeState())

    def candidates(self, role: str, preferred: list[str] | None = None) -> list[ProviderProfile]:
        aliases = preferred or self.routes.get(role) or self.routes["orchestrator"]
        result: list[ProviderProfile] = []
        seen_health_keys: set[str] = set()
        now = time.time()
        for alias in aliases:
            profile = self.profiles.get(alias)
            if not profile or not profile.available():
                continue
            if profile.health_key() in seen_health_keys:
                continue
            state = self.state_for(profile.alias)
            if state.permanently_disabled or state.open_until > now:
                continue
            seen_health_keys.add(profile.health_key())
            result.append(profile)
        return result

    def record_success(self, alias: str) -> None:
        state = self.states.setdefault(alias, ProviderRuntimeState())
        state.consecutive_failures = 0
        state.open_until = 0.0
        state.last_error = None
        state.last_success_at = time.time()
        state.total_successes += 1

    @staticmethod
    def classify_failure(error: Exception | str) -> str:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code in {401, 403}:
            return "auth"
        if status_code in {404, 410}:
            return "permanent"
        if status_code == 429:
            return "rate_limit"
        if isinstance(error, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
            return "transient"
        if isinstance(status_code, int) and 500 <= status_code <= 599:
            return "transient"
        message = str(error).lower()
        if any(token in message for token in ("401", "403", "invalid api key", "authentication", "unauthorized", "forbidden")):
            return "auth"
        if any(token in message for token in ("404", "410", "model not found", "not found")):
            return "permanent"
        if "429" in message or "rate limit" in message or "retry-after" in message:
            return "rate_limit"
        if any(token in message for token in ("timeout", "timed out", "capacity", "overloaded", "empty response", "empty output", "temporarily unavailable")) or re.search(r"\b5\d{2}\b", message):
            return "transient"
        return "other"

    @staticmethod
    def retry_after_seconds(error: Exception | str, default: float = 1.0) -> float:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            header_value = headers.get("Retry-After")
            if header_value:
                return ProviderRegistry._parse_retry_after_value(str(header_value), default)

        match = re.search(r"retry[-_ ]?after\s*[:= ]\s*(\d+(?:\.\d+)?)", str(error), flags=re.IGNORECASE)
        if match:
            return ProviderRegistry._parse_retry_after_value(match.group(1), default)
        date_match = re.search(
            r"retry[-_ ]?after\s*[:= ]\s*([A-Za-z]{3},[^\n\r]+)",
            str(error),
            flags=re.IGNORECASE,
        )
        if date_match:
            try:
                delay = parsedate_to_datetime(date_match.group(1)).timestamp() - time.time()
                return max(0.0, min(delay, 30.0))
            except (TypeError, ValueError, OverflowError):
                return default
        return default

    @staticmethod
    def _parse_retry_after_value(value: str, default: float) -> float:
        try:
            return max(0.0, min(float(value), 30.0))
        except ValueError:
            try:
                delay = parsedate_to_datetime(value).timestamp() - time.time()
                return max(0.0, min(delay, 30.0))
            except (TypeError, ValueError, OverflowError):
                return default

    def record_failure(self, alias: str, error: Exception | str) -> str:
        state = self.state_for(alias)
        state.consecutive_failures += 1
        state.total_failures += 1
        state.last_error = redact_text(str(error))
        kind = self.classify_failure(error)
        if kind == "permanent":
            state.permanently_disabled = True
            state.open_until = 0.0
            return kind
        auth_failure = kind == "auth"
        capacity_failure = kind in {"rate_limit", "transient"}
        if auth_failure:
            cooldown = 900.0
        elif capacity_failure:
            cooldown = min(300.0, 20.0 * state.consecutive_failures)
        else:
            cooldown = min(120.0, 5.0 * state.consecutive_failures)
        if auth_failure or capacity_failure or state.consecutive_failures >= 2:
            state.open_until = time.time() + cooldown
        return kind

    def refresh(self, alias: str | None = None) -> None:
        names = [alias] if alias else list(self.profiles)
        for name in names:
            state = self.state_for(name)
            state.consecutive_failures = 0
            state.open_until = 0.0
            state.last_error = None
            state.permanently_disabled = False

    async def verify_runtime(self, alias: str) -> dict[str, Any]:
        """Verify health/readiness and the exact configured model without logging secrets."""
        profile = self.get(alias)
        if profile.transport in {"oauth", "web"}:
            profile.runtime_verified = True
            return {"alias": alias, "verified": True, "reason": "non-api transport"}
        if not profile.base_url:
            profile.runtime_verified = False
            return {"alias": alias, "verified": False, "reason": "missing base URL"}
        key = profile.api_key()
        if profile.auth_required and not key:
            profile.runtime_verified = False
            return {"alias": alias, "verified": False, "reason": "missing API key"}

        headers = {"Accept": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        base = profile.base_url.rstrip("/")
        checks: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                if alias.startswith("ds2api-"):
                    root = base.removesuffix("/v1")
                    for name in ("healthz", "readyz"):
                        response = await client.get(f"{root}/{name}", headers=headers)
                        checks[name] = {"status": response.status_code, "ok": response.is_success}
                        response.raise_for_status()
                response = await client.get(f"{base}/models", headers=headers)
                checks["models"] = {"status": response.status_code, "ok": response.is_success}
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            profile.runtime_verified = False
            self.record_failure(alias, str(exc))
            return {"alias": alias, "verified": False, "checks": checks, "reason": redact_text(str(exc))}

        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        model_ids = {
            str(item.get("id"))
            for item in rows
            if isinstance(item, dict) and item.get("id")
        }
        verified = profile.model in model_ids
        profile.runtime_verified = verified
        if verified:
            self.record_success(alias)
        else:
            self.record_failure(alias, f"runtime model not found: {profile.model}")
        return {
            "alias": alias,
            "model": profile.model,
            "verified": verified,
            "runtime_model_count": len(model_ids),
            "checks": checks,
            "reason": None if verified else "exact model ID was not returned by /v1/models",
        }

    def status(self) -> list[dict[str, Any]]:
        now = time.time()
        rows: list[dict[str, Any]] = []
        for alias, profile in self.profiles.items():
            state = self.state_for(alias)
            rows.append(
                {
                    "alias": alias,
                    "display_name": profile.display_name,
                    "transport": profile.transport,
                    "model": profile.model,
                    "health_key": profile.health_key(),
                    "available": profile.available(),
                    "runtime_required": profile.runtime_required,
                    "runtime_verified": profile.runtime_verified,
                    "advisory_only": profile.advisory_only,
                    "roles": profile.roles,
                    "circuit_open": state.open_until > now,
                    "open_for_seconds": max(0.0, state.open_until - now),
                    "consecutive_failures": state.consecutive_failures,
                    "last_error": state.last_error,
                    "last_success_at": state.last_success_at,
                    "total_successes": state.total_successes,
                    "total_failures": state.total_failures,
                    "permanently_disabled": state.permanently_disabled,
                }
            )
        return rows
