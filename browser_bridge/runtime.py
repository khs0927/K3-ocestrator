from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

from .profiles import BrowserProfile


class BrowserRuntimeError(RuntimeError):
    pass


class BrowserChatRuntime:
    def __init__(self, profile: BrowserProfile, data_dir: Path, *, headless: bool = False) -> None:
        self.profile = profile
        self.data_dir = data_dir / profile.id
        self.headless = headless
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def start(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserRuntimeError("Playwright is not installed; install requirements-browser.txt") from exc
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.data_dir),
            headless=self.headless,
            viewport={"width": 1440, "height": 1000},
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._playwright = None
        self._page = None

    async def open_for_login(self) -> None:
        await self.start()
        await self._page.goto(self.profile.url, wait_until="domcontentloaded")
        await self._page.bring_to_front()

    async def _first_visible(self, selectors: list[str]) -> Any:
        assert self._page is not None
        for selector in selectors:
            locator = self._page.locator(selector)
            count = await locator.count()
            for index in range(count - 1, -1, -1):
                item = locator.nth(index)
                try:
                    if await item.is_visible():
                        return item
                except Exception:
                    continue
        raise BrowserRuntimeError(
            f"No visible element found. Update selectors for {self.profile.id} in config/browser-profiles.json"
        )

    async def _assistant_texts(self) -> list[str]:
        assert self._page is not None
        texts: list[str] = []
        seen: set[str] = set()
        for selector in self.profile.assistant_selectors:
            locator = self._page.locator(selector)
            count = await locator.count()
            for index in range(count):
                try:
                    item = locator.nth(index)
                    if not await item.is_visible():
                        continue
                    text = (await item.inner_text()).strip()
                    if text and text not in seen:
                        seen.add(text)
                        texts.append(text)
                except Exception:
                    continue
        return texts

    async def chat(self, prompt: str) -> str:
        async with self._lock:
            await self.start()
            assert self._page is not None
            current = urlparse(self._page.url)
            expected = urlparse(self.profile.url)
            if current.scheme != expected.scheme or current.hostname != expected.hostname or current.port != expected.port:
                await self._page.goto(self.profile.url, wait_until="domcontentloaded")
            wait = self.profile.request_delay_seconds - (time.time() - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            before = await self._assistant_texts()
            input_box = await self._first_visible(self.profile.input_selectors)
            try:
                await input_box.fill(prompt)
            except Exception:
                await input_box.click()
                await self._page.keyboard.press("Control+A")
                await self._page.keyboard.type(prompt)
            if self.profile.send_method == "enter":
                await input_box.press("Enter")
            else:
                await self._page.keyboard.press("Enter")
            self._last_request_at = time.time()

            deadline = time.monotonic() + self.profile.response_timeout_seconds
            last_text = ""
            stable_since = time.monotonic()
            while time.monotonic() < deadline:
                await asyncio.sleep(1.0)
                current = await self._assistant_texts()
                candidate = current[-1] if current else ""
                is_new = len(current) > len(before) or (candidate and candidate not in before)
                if not is_new:
                    continue
                if candidate != last_text:
                    last_text = candidate
                    stable_since = time.monotonic()
                elif last_text and time.monotonic() - stable_since >= self.profile.stable_seconds:
                    return last_text
            raise BrowserRuntimeError(
                f"Timed out waiting for {self.profile.display_name}. Log in or update selectors."
            )
