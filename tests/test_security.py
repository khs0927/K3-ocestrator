from pathlib import Path

import pytest

from app.audit import AuditLogger
from app.security import PathSecurityError, redact_payload, redact_text, resolve_allowed_path


def test_allowed_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "a.txt"
    assert resolve_allowed_path(target, [root]) == target.resolve()


def test_reject_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PathSecurityError):
        resolve_allowed_path(tmp_path / "outside.txt", [root])


def test_redact_text_removes_credentials_from_errors() -> None:
    value = (
        "Authorization: Bearer bearer-secret, api_key=nvapi-test-secret "
        'password="password-secret" token=jwt-secret'
    )
    redacted = redact_text(value)
    assert "bearer-secret" not in redacted
    assert "nvapi-test-secret" not in redacted
    assert "password-secret" not in redacted
    assert "jwt-secret" not in redacted
    assert "[REDACTED]" in redacted or "[REDACTED_API_KEY]" in redacted
    header_error = "Headers({'authorization': 'Bearer header-secret', 'x-api-key': 'x-secret'})"
    assert "header-secret" not in redact_text(header_error)
    assert "x-secret" not in redact_text(header_error)


def test_redact_payload_and_audit_logger_do_not_persist_credentials(tmp_path: Path) -> None:
    payload = {"error": "Bearer secret-token", "nested": ["password=secret-password"]}
    redacted = redact_payload(payload)
    assert "secret-token" not in str(redacted)
    assert "secret-password" not in str(redacted)

    audit = AuditLogger(tmp_path / "audit.jsonl")
    audit.write("provider_failure", **payload)
    content = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "secret-token" not in content
    assert "secret-password" not in content
