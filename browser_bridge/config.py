from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BrowserBridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    browser_bridge_host: str = "127.0.0.1"
    browser_bridge_port: int = 8788
    browser_bridge_api_key: str = ""
    browser_bridge_headless: bool = False
    browser_bridge_profiles_file: Path = Path("./config/browser-profiles.json")
    browser_bridge_data_dir: Path = Path("./data/browser-bridge")

    def prepare(self) -> None:
        self.browser_bridge_data_dir.mkdir(parents=True, exist_ok=True)
        self.browser_bridge_profiles_file.parent.mkdir(parents=True, exist_ok=True)


settings = BrowserBridgeSettings()
