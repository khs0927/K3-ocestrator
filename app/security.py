from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Any, Iterable


class PathSecurityError(ValueError):
    pass


_SENSITIVE_TEXT_PATTERNS = (
    (
        re.compile(r"(?i)(\bauthorization[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?)[^\s,;}\]]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)(\bbearer\s+)[^\s,;}\]]+"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)([\"']?(?:x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|jwt[_-]?secret)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;}\]]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)([?&](?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)=)[^&\s]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\bnvapi-[A-Za-z0-9_-]+"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]+"), "[REDACTED_API_KEY]"),
)
_SENSITIVE_PAYLOAD_KEYS = re.compile(
    r"(?i)^(?:authorization|x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|jwt[_-]?secret|cookie)$"
)


def redact_text(value: str) -> str:
    """Remove common credential forms before text reaches logs or API errors."""
    redacted = value
    for pattern, replacement in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_payload(value: Any) -> Any:
    """Recursively redact strings in structured audit/API payloads."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_PAYLOAD_KEYS.fullmatch(str(key).strip()):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(item) for item in value)
    return value


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
