from pathlib import Path

import pytest

from app.security import PathSecurityError, resolve_allowed_path


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
