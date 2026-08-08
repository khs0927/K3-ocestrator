from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BrowserProfile(BaseModel):
    id: str
    display_name: str
    url: str
    model: str
    input_selectors: list[str]
    assistant_selectors: list[str]
    send_method: str = "enter"
    request_delay_seconds: float = Field(default=3.0, ge=0)
    response_timeout_seconds: float = Field(default=600.0, ge=10)
    stable_seconds: float = Field(default=3.0, ge=0.5)


DEFAULTS = {
    "deepseek": BrowserProfile(
        id="deepseek",
        display_name="DeepSeek Web",
        url="https://chat.deepseek.com/",
        model="deepseek-web",
        input_selectors=[
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true']",
        ],
        assistant_selectors=[
            "[data-role='assistant']",
            "[data-message-author-role='assistant']",
            ".ds-markdown",
            ".markdown-body",
            ".prose",
        ],
    ),
    "glm": BrowserProfile(
        id="glm",
        display_name="GLM Web",
        url="https://chat.z.ai/",
        model="glm-web",
        input_selectors=[
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true']",
        ],
        assistant_selectors=[
            "[data-role='assistant']",
            "[data-message-author-role='assistant']",
            ".markdown-body",
            ".prose",
            "article",
        ],
    ),
}


def load_profiles(path: Path) -> dict[str, BrowserProfile]:
    profiles = dict(DEFAULTS)
    if not path.exists():
        return profiles
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return profiles
    if isinstance(data, dict):
        data = data.get("profiles", data)
    if not isinstance(data, dict):
        return profiles
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        base: dict[str, Any] = profiles.get(key, BrowserProfile(
            id=str(key), display_name=str(key), url="", model=f"{key}-web",
            input_selectors=["textarea"], assistant_selectors=[".prose"]
        )).model_dump()
        base.update(value)
        profiles[str(key)] = BrowserProfile.model_validate(base)
    return profiles
