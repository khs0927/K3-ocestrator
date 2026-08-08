#!/usr/bin/env python3
"""Run a bounded exact-model provider gate without printing credentials or content."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request


DEFAULTS = {
    "kimi": ("https://api.moonshot.ai/v1", "kimi-k3", "KIMI_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "deepseek-ai/deepseek-v4-flash", "NVIDIA_API_KEY"),
    "ds2api": ("http://127.0.0.1:5001/v1", "deepseek-v4-flash", "DS2API_API_KEY"),
    "zai": ("https://api.z.ai/api/paas/v4", "glm-5.2", "ZAI_API_KEY"),
}


def request_json(url: str, method: str = "GET", payload: dict | None = None, key: str = "") -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return 0, None


def main() -> int:
    parser = argparse.ArgumentParser(description="run exact-model provider health and synthetic chat checks")
    parser.add_argument("provider", choices=tuple(DEFAULTS))
    parser.add_argument("--model", default="")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    default_base, default_model, key_name = DEFAULTS[args.provider]
    base = os.getenv(f"{args.provider.upper()}_BASE_URL", default_base).rstrip("/")
    model = args.model or os.getenv(f"{args.provider.upper()}_MODEL", default_model)
    key = os.getenv(key_name, "").strip()
    if args.provider != "ds2api" and not key:
        print(json.dumps({"ok": False, "provider": args.provider, "error": "missing provider key"}))
        return 2

    probes: dict[str, int] = {}
    if args.provider == "ds2api":
        root = base.removesuffix("/v1")
        for name in ("healthz", "readyz"):
            status, _ = request_json(f"{root}/{name}", key=key)
            probes[name] = status
            if not 200 <= status < 400:
                print(json.dumps({"ok": False, "provider": args.provider, "error": f"{name} failed", "status": status}))
                return 1

    status, models_payload = request_json(f"{base}/models", key=key)
    rows = models_payload.get("data", []) if isinstance(models_payload, dict) else []
    model_ids = {str(item.get("id")) for item in rows if isinstance(item, dict) and item.get("id")}
    if not 200 <= status < 400 or model not in model_ids:
        print(json.dumps({
            "ok": False,
            "provider": args.provider,
            "model": model,
            "status": status,
            "runtime_model_count": len(model_ids),
            "probes": probes,
            "error": "exact model ID was not returned by /v1/models",
        }))
        return 1

    successes = 0
    latencies: list[int] = []
    for _ in range(max(1, args.count)):
        started = time.monotonic()
        status, payload = request_json(
            f"{base}/chat/completions",
            method="POST",
            key=key,
            payload={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK only."}],
                "max_tokens": 64,
                "temperature": 0.2,
            },
        )
        choices = payload.get("choices", []) if isinstance(payload, dict) else []
        content = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = str(message.get("content", ""))
        if 200 <= status < 300 and content.strip():
            successes += 1
            latencies.append(int((time.monotonic() - started) * 1000))

    result = {
        "ok": successes == max(1, args.count),
        "provider": args.provider,
        "model": model,
        "runtime_model_count": len(model_ids),
        "probes": probes,
        "successes": successes,
        "requested": max(1, args.count),
        "latency_ms": {"min": min(latencies) if latencies else None, "max": max(latencies) if latencies else None},
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
