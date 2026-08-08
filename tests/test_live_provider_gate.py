from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_gate() -> ModuleType:
    script = Path(__file__).parents[1] / "scripts" / "live-provider-gate.py"
    spec = importlib.util.spec_from_file_location("live_provider_gate", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_gate_verifies_ds2api_contract_and_ten_chats(monkeypatch, capsys) -> None:
    gate = _load_gate()
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request_json(url: str, method: str = "GET", payload: dict | None = None, key: str = ""):
        calls.append((url, method, payload))
        if url.endswith("/healthz") or url.endswith("/readyz"):
            return 200, {"status": "ok"}
        if url.endswith("/models"):
            return 200, {"data": [{"id": "deepseek-v4-flash"}]}
        if url.endswith("/chat/completions"):
            assert method == "POST"
            assert payload is not None and payload["model"] == "deepseek-v4-flash"
            return 200, {"choices": [{"message": {"content": "OK"}}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(gate, "request_json", fake_request_json)
    monkeypatch.setenv("DS2API_BASE_URL", "http://mock-ds2api:5001/v1")
    monkeypatch.setenv("DS2API_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(sys, "argv", ["live-provider-gate.py", "ds2api", "--count", "10"])

    assert gate.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["successes"] == 10
    assert payload["probes"] == {"healthz": 200, "readyz": 200}
    assert len([item for item in calls if item[0].endswith("/chat/completions")]) == 10


def test_live_gate_fails_closed_on_exact_model_mismatch(monkeypatch, capsys) -> None:
    gate = _load_gate()

    def fake_request_json(url: str, method: str = "GET", payload: dict | None = None, key: str = ""):
        if url.endswith("/healthz") or url.endswith("/readyz"):
            return 200, {"status": "ok"}
        if url.endswith("/models"):
            return 200, {"data": [{"id": "deepseek-v4-flash"}]}
        raise AssertionError("chat must not be attempted when the exact model is absent")

    monkeypatch.setattr(gate, "request_json", fake_request_json)
    monkeypatch.setenv("DS2API_BASE_URL", "http://mock-ds2api:5001/v1")
    monkeypatch.setattr(sys, "argv", ["live-provider-gate.py", "ds2api", "--model", "wrong-model", "--count", "10"])

    assert gate.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "exact model ID was not returned by /v1/models"
    assert payload["model"] == "wrong-model"


def test_live_gate_secret_file_fallback_and_direct_precedence(tmp_path, monkeypatch) -> None:
    gate = _load_gate()
    secret = tmp_path / "nvidia-key"
    secret.write_text("file-key\n", encoding="utf-8")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY_FILE", str(secret))
    assert gate.secret_from_env("NVIDIA_API_KEY") == "file-key"

    monkeypatch.setenv("NVIDIA_API_KEY", "direct-key")
    assert gate.secret_from_env("NVIDIA_API_KEY") == "direct-key"
