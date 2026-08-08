from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_watchdog():
    script = Path(__file__).parents[1] / "scripts" / "watchdog.py"
    spec = importlib.util.spec_from_file_location("watchdog", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_watchdog_secret_file_fallback_and_direct_precedence(tmp_path, monkeypatch):
    watchdog = _load_watchdog()
    secret = tmp_path / "gateway-key"
    secret.write_text("file-gateway-key\n", encoding="utf-8")
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    monkeypatch.setenv("GATEWAY_API_KEY_FILE", str(secret))
    assert watchdog.secret_from_env("GATEWAY_API_KEY") == "file-gateway-key"

    monkeypatch.setenv("GATEWAY_API_KEY", "direct-gateway-key")
    assert watchdog.secret_from_env("GATEWAY_API_KEY") == "direct-gateway-key"
