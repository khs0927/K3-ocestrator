from pathlib import Path

from app.config import Settings
from app.models import OrchestrationMode
from app.policy import decide_permission


def make_settings() -> Settings:
    return Settings(_env_file=None, default_workspace=Path("./workspace"), gateway_api_key="test")


def test_plan_allows_read_and_denies_execute() -> None:
    settings = make_settings()
    assert decide_permission(OrchestrationMode.plan, "read", "Read", {}, settings).action == "allow"
    assert decide_permission(OrchestrationMode.plan, "execute", "Bash", {"command": "ls"}, settings).action == "deny"


def test_review_requires_approval_for_tests() -> None:
    decision = decide_permission(OrchestrationMode.review, "execute", "Run tests", {"command": "pytest -q"}, make_settings())
    assert decision.action == "ask"


def test_execute_allows_plain_git_status_and_asks_for_write() -> None:
    settings = make_settings()
    assert decide_permission(OrchestrationMode.execute, "execute", "Status", {"command": "git status --short"}, settings).action == "allow"
    assert decide_permission(OrchestrationMode.execute, "edit", "Edit file", {"path": "a.py"}, settings).action == "ask"


def test_auto_allow_rejects_command_chaining() -> None:
    decision = decide_permission(OrchestrationMode.execute, "execute", "Status", {"command": "git status && rm -rf workspace"}, make_settings())
    assert decision.action == "ask"


def test_auto_allow_rejects_git_config_and_external_diff() -> None:
    settings = make_settings()
    for command in ("git -c core.pager=cat status", "git diff --ext-diff", "git diff --textconv"):
        assert decide_permission(OrchestrationMode.execute, "execute", "Git", {"command": command}, settings).action == "ask"
