from __future__ import annotations

import httpx

from .models import OrchestrationMode
from .providers import ProviderProfile


class WebAdvisoryClient:
    """OpenAI-compatible personal browser bridge fallback.

    This path is advisory only. It never receives local tools, filesystem access, or
    execute/yolo tasks, and it must not be used to bypass service limits or CAPTCHA.
    """

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def chat(self, profile: ProviderProfile, prompt: str, mode: OrchestrationMode) -> str:
        if mode in {OrchestrationMode.execute, OrchestrationMode.yolo}:
            raise RuntimeError("Web advisory profiles cannot execute code changes")
        if not profile.base_url:
            raise RuntimeError(f"Web bridge URL is not configured for {profile.alias}")
        headers: dict[str, str] = {}
        key = profile.api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{profile.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": profile.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
