#!/usr/bin/env python3
"""Bounded heartbeat watchdog for the gateway and optional DS2API service."""
from __future__ import annotations

import argparse
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


def check_url(url: str, timeout: float, headers: dict[str, str] | None = None) -> dict[str, object]:
    request = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 400, "status": response.status}
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        status = getattr(exc, "code", None)
        return {"ok": False, "status": status, "error": type(exc).__name__}


def run_once(output_path: Path, timeout: float) -> int:
    gateway = os.getenv("WATCHDOG_GATEWAY_URL", "http://127.0.0.1:8790").rstrip("/")
    gateway_key = os.getenv("GATEWAY_API_KEY", "").strip()
    gateway_headers = {"Accept": "application/json"}
    if gateway_key:
        gateway_headers["Authorization"] = f"Bearer {gateway_key}"
    checks: dict[str, object] = {
        "gateway": check_url(f"{gateway}/health", timeout, gateway_headers),
    }

    ds2api_enabled = os.getenv("DS2API_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    ds2api = os.getenv("DS2API_BASE_URL", "").rstrip("/")
    if ds2api_enabled and ds2api:
        root = ds2api.removesuffix("/v1")
        ds2api_key = os.getenv("DS2API_API_KEY", "").strip()
        headers = {"Accept": "application/json"}
        if ds2api_key:
            headers["Authorization"] = f"Bearer {ds2api_key}"
        checks["ds2api_healthz"] = check_url(f"{root}/healthz", timeout, headers)
        checks["ds2api_readyz"] = check_url(f"{root}/readyz", timeout, headers)

    ok = all(isinstance(value, dict) and value.get("ok") for value in checks.values())
    payload = {"timestamp": time.time(), "ok": ok, "checks": checks}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="check gateway and DS2API liveness")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--heartbeat", default=os.getenv("WATCHDOG_HEARTBEAT", "./data/watchdog-heartbeat.json"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    heartbeat = Path(args.heartbeat)
    if args.once:
        return run_once(heartbeat, args.timeout)
    while True:
        run_once(heartbeat, args.timeout)
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
