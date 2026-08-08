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


def test_provider_compose_wires_root_only_gateway_and_ds2api_secrets():
    text = Path("docker-compose.providers.yml").read_text(encoding="utf-8")
    assert "GATEWAY_API_KEY_FILE: /run/secrets/gateway_api_key" in text
    assert "DS2API_JWT_SECRET_FILE: /run/secrets/ds2api_jwt_secret" in text
    assert "GATEWAY_API_KEY_FILE: /run/secrets/gateway_api_key" in text
    assert "DS2API_API_KEY_FILE: /run/secrets/ds2api_api_key" in text
    assert "cat \"$${GATEWAY_API_KEY_FILE}\"" in text
    assert "gateway_api_key:" in text
    assert "ds2api_jwt_secret:" in text
    assert "GATEWAY_API_KEY_FILE:?set" in text
    assert "--fail-fast" in text
    assert "DS2API_JWT_SECRET_FILE:?set" in text
    assert "http://127.0.0.1:8790/ready" in text
    assert "http://127.0.0.1:5001/readyz" in text
    assert "deepseek-v4-flash" in text


def test_systemd_recovery_templates_cover_gateway_and_ds2api():
    service = Path("deploy/k3-orchestrator-health-recover@.service").read_text(encoding="utf-8")
    timer = Path("deploy/k3-orchestrator-health-recover@.timer").read_text(encoding="utf-8")
    assert "Environment=SERVICE=%i" in service
    assert "Environment=COMPOSE_ENV_FILE=/etc/k3-secrets/provider.env" in service
    assert "Environment=GATEWAY_ENV_FILE=/etc/k3-secrets/gateway.env" in service
    assert "compose-health-recover.sh" in service
    assert "OnUnitActiveSec=1min" in timer
