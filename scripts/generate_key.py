from __future__ import annotations

import secrets
from pathlib import Path

path = Path(".env")
if not path.exists():
    path.write_text(Path(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
text = path.read_text(encoding="utf-8")
changed = False
for placeholder in (
    "CHANGE_TO_A_LONG_RANDOM_LOCAL_KEY",
    "CHANGE_TO_A_SECOND_LOCAL_KEY",
):
    if placeholder in text:
        text = text.replace(placeholder, secrets.token_urlsafe(48))
        changed = True
if changed:
    path.write_text(text, encoding="utf-8")
    print("Generated local gateway/bridge keys in .env")
else:
    print(".env already has non-placeholder local keys; unchanged")
