from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import __version__
from .config import settings
from .providers import ProviderRegistry


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _masked_secret_state(value: str) -> str:
    value = value.strip()
    if not value:
        return "missing"
    if value.startswith("CHANGE_"):
        return "placeholder"
    return "configured"


def main() -> int:
    settings.prepare()
    registry = ProviderRegistry.load(settings.provider_profiles_file, settings.routing_file)
    secret_values = {
        "NVIDIA_API_KEY": settings.nvidia_api_key,
        "DEEPSEEK_API_KEY": settings.deepseek_api_key,
        "ZAI_API_KEY": settings.zai_api_key,
        "DS2API_API_KEY": settings.resolved_ds2api_api_key(),
        "DEEPSEEK_WEB_BRIDGE_KEY": settings.deepseek_web_bridge_key,
        "GLM_WEB_BRIDGE_KEY": settings.glm_web_bridge_key,
    }
    for profile in registry.profiles.values():
        if profile.api_key_env:
            profile.bind_api_key(secret_values.get(profile.api_key_env))
    ds2api = registry.profiles.get("ds2api-deepseek-v4-flash")
    if ds2api is not None:
        ds2api.base_url = settings.ds2api_base_url.rstrip("/")
        ds2api.enabled = settings.ds2api_enabled
    for alias, url in {
        "deepseek-web-advisory": settings.deepseek_web_bridge_url,
        "glm-web-advisory": settings.glm_web_bridge_url,
    }.items():
        profile = registry.profiles.get(alias)
        if profile:
            profile.base_url = url.strip() or None
            profile.enabled = settings.enable_web_advisory_fallback and bool(url.strip())

    kimi = shutil.which(settings.kimi_command)
    warnings: list[str] = []
    report: dict[str, Any] = {
        "gateway_version": __version__,
        "kimi_command": kimi,
        "kimi_code_home": str(settings.kimi_code_home.resolve()),
        "default_workspace": str(settings.default_workspace.resolve()),
        "gateway": {
            "host": settings.gateway_host,
            "port": settings.gateway_port,
            "api_key": _masked_secret_state(settings.gateway_api_key),
        },
        "provider_credentials": {
            "nvidia": _masked_secret_state(settings.nvidia_api_key),
            "deepseek": _masked_secret_state(settings.deepseek_api_key),
            "zai": _masked_secret_state(settings.zai_api_key),
            "ds2api": _masked_secret_state(settings.resolved_ds2api_api_key()),
        },
        "dependencies": {
            "agent-client-protocol": _version("agent-client-protocol"),
            "mcp": _version("mcp"),
            "fastapi": _version("fastapi"),
            "pydantic": _version("pydantic"),
            "playwright_optional": _version("playwright"),
        },
        "providers": registry.status(),
        "routes": registry.routes,
        "warnings": warnings,
    }

    if not kimi:
        warnings.append("Kimi Code is not installed or is missing from PATH")
    else:
        try:
            completed = subprocess.run(
                [kimi, "--version"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            report["kimi_version"] = (completed.stdout or completed.stderr).strip()
            report["kimi_version_exit_code"] = completed.returncode
            if completed.returncode != 0:
                warnings.append("kimi --version returned a non-zero exit code")
        except (OSError, subprocess.TimeoutExpired) as exc:
            warnings.append(f"Unable to run kimi --version: {exc}")

    if _masked_secret_state(settings.gateway_api_key) != "configured":
        warnings.append("GATEWAY_API_KEY is missing or still an example placeholder")
    if _version("agent-client-protocol") is None:
        warnings.append("agent-client-protocol is not installed")
    if _version("mcp") is None:
        warnings.append("mcp Python SDK is not installed")
    if settings.enable_web_advisory_fallback and _version("playwright") is None:
        warnings.append("Web advisory fallback is enabled but Playwright is not installed")
    if not Path(settings.default_workspace).exists():
        warnings.append("Default workspace does not exist")

    report["available_provider_aliases"] = [
        row["alias"] for row in report["providers"] if row["available"]
    ]
    report["ok"] = not any(
        text.startswith("Kimi Code is not installed")
        or text.startswith("agent-client-protocol is not installed")
        or text.startswith("mcp Python SDK is not installed")
        for text in warnings
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
