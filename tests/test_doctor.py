from __future__ import annotations

from pathlib import Path

from app.config import kimi_oauth_credentials_present
from app.doctor import _masked_secret_state


def test_doctor_masks_missing_optional_secret_without_crashing():
    assert _masked_secret_state(None) == "missing"
    assert _masked_secret_state("") == "missing"
    assert _masked_secret_state("configured-value") == "configured"


def test_kimi_oauth_presence_checks_metadata_only(tmp_path: Path):
    home = tmp_path / "kimi-code"
    assert kimi_oauth_credentials_present(home) is False
    (home / "credentials").mkdir(parents=True)
    assert kimi_oauth_credentials_present(home) is False
    (home / "credentials" / "kimi-code.json").write_text("{}", encoding="utf-8")
    assert kimi_oauth_credentials_present(home) is True
