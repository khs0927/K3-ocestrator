from __future__ import annotations

from pathlib import Path


def test_compose_keeps_gateway_local_and_unprivileged():
    text = Path("docker-compose.sandbox.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8790:8790"' in text
    assert 'user: "10001:10001"' in text
    assert "read_only: true" in text
    assert "no-new-privileges:true" in text
    assert "cap_drop:" in text and "- ALL" in text
    assert "ALLOW_YOLO_MODE: \"false\"" in text
    assert "/var/run/docker.sock" not in text
    assert "./workspace:/workspace:rw" in text


def test_docker_context_excludes_secrets_and_runtime_state():
    text = Path(".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in text
    assert "data" in text
    assert "workspace" in text
    assert "config/provider-profiles.json" in text
