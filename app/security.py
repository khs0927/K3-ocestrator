from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Iterable


class PathSecurityError(ValueError):
    pass


def resolve_allowed_path(path: str | Path, roots: Iterable[Path], *, must_exist: bool = False) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=must_exist)
    allowed = False
    for root in roots:
        resolved_root = root.expanduser().resolve()
        try:
            candidate.relative_to(resolved_root)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise PathSecurityError(f"Path is outside configured workspace roots: {candidate}")
    return candidate


def lock_down_file(path: Path) -> None:
    try:
        path.chmod(0o600)
        path.parent.chmod(0o700)
    except OSError:
        pass


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(content, encoding="utf-8")
    lock_down_file(tmp)
    tmp.replace(path)
    lock_down_file(path)


def verify_bearer(provided_header: str | None, expected: str) -> bool:
    if not expected:
        return True
    provided = ""
    if provided_header and provided_header.lower().startswith("bearer "):
        provided = provided_header[7:].strip()
    return secrets.compare_digest(provided, expected)
