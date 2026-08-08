from __future__ import annotations

import argparse
import asyncio

from .config import settings
from .profiles import load_profiles
from .runtime import BrowserChatRuntime


async def main_async(provider_id: str) -> None:
    settings.prepare()
    profiles = load_profiles(settings.browser_bridge_profiles_file)
    if provider_id not in profiles:
        raise SystemExit(f"Unknown provider {provider_id}; choices: {', '.join(profiles)}")
    runtime = BrowserChatRuntime(
        profiles[provider_id],
        settings.browser_bridge_data_dir,
        headless=False,
    )
    await runtime.open_for_login()
    print(f"Opened {profiles[provider_id].display_name}. Log in manually, open a new chat, then press Enter here.")
    await asyncio.to_thread(input)
    await runtime.close()
    print("Browser profile saved locally. No password or cookie was exported.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=["deepseek", "glm"])
    args = parser.parse_args()
    asyncio.run(main_async(args.provider))


if __name__ == "__main__":
    main()
