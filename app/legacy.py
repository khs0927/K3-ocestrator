from __future__ import annotations

import httpx

from .config import Settings
from .models import OrchestrationMode


class LegacyWebFallback:
    """Read-only fallback to the previous browser-session bridge.

    It is deliberately disabled for execute/yolo modes because it has no structured
    tool permissions or reliable code-session semantics.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def chat(self, prompt: str, mode: OrchestrationMode) -> str:
        if mode in {OrchestrationMode.execute, OrchestrationMode.yolo}:
            raise RuntimeError("Legacy web fallback cannot execute code changes")
        headers = {}
        if self.settings.legacy_web_bridge_key:
            headers["Authorization"] = f"Bearer {self.settings.legacy_web_bridge_key}"
        async with httpx.AsyncClient(timeout=self.settings.prompt_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.legacy_web_bridge_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": "kimi-k3-web",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
