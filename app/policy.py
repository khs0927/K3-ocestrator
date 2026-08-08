from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Iterable

from .config import Settings
from .models import OrchestrationMode


@dataclass(frozen=True)
class PolicyDecision:
    action: str  # allow | deny | ask
    reason: str


def _normalise_command(raw_input: Any) -> str:
    if isinstance(raw_input, str):
        return " ".join(raw_input.strip().split())
    if isinstance(raw_input, dict):
        command = raw_input.get("command") or raw_input.get("cmd") or raw_input.get("script")
        args = raw_input.get("args")
        if isinstance(command, str) and isinstance(args, list):
            return " ".join([command, *(shlex.quote(str(item)) for item in args)])
        if isinstance(command, str):
            return " ".join(command.strip().split())
    return ""


def _tokens(value: str) -> list[str]:
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return []


def _contains_shell_control(command: str) -> bool:
    # Safe auto-approval accepts a single process only. Pipelines, redirections,
    # substitutions and command chaining must go through explicit approval.
    return any(token in command for token in ("&&", "||", ";", "\n", "\r", "`", "$(", "|", ">", "<", "&"))


def _dangerous_git_tokens(tokens: list[str]) -> bool:
    dangerous_exact = {"-c", "--ext-diff", "--textconv", "--exec-path", "--upload-pack", "--receive-pack"}
    dangerous_prefixes = ("--config-env=", "--exec-path=", "--upload-pack=", "--receive-pack=")
    return any(token in dangerous_exact or token.startswith(dangerous_prefixes) for token in tokens)


def _matches_safe_prefix(command: str, prefixes: Iterable[str]) -> bool:
    if not command or _contains_shell_control(command):
        return False
    command_tokens = _tokens(command)
    if not command_tokens:
        return False
    if command_tokens[0].lower() == "git" and _dangerous_git_tokens(command_tokens[1:]):
        return False
    for prefix in prefixes:
        prefix_tokens = _tokens(prefix)
        if prefix_tokens and [t.lower() for t in command_tokens[: len(prefix_tokens)]] == [
            t.lower() for t in prefix_tokens
        ]:
            return True
    return False


def decide_permission(
    mode: OrchestrationMode,
    kind: str | None,
    title: str,
    raw_input: Any,
    settings: Settings,
) -> PolicyDecision:
    tool_kind = (kind or "other").lower()
    command = _normalise_command(raw_input)

    if mode is OrchestrationMode.yolo:
        if settings.allow_yolo_mode:
            return PolicyDecision("allow", "YOLO mode explicitly enabled")
        return PolicyDecision("deny", "YOLO mode is disabled by gateway policy")

    safe_non_mutating = {"read", "search", "fetch", "think", "switch_mode"}
    mutating = {"edit", "delete", "move"}

    if mode is OrchestrationMode.plan:
        if tool_kind in safe_non_mutating:
            return PolicyDecision("allow", "Planning mode permits read-only tools")
        return PolicyDecision("deny", "Planning mode blocks file changes and command execution")

    if mode is OrchestrationMode.review:
        if tool_kind in safe_non_mutating:
            return PolicyDecision("allow", "Review mode permits read-only tools")
        if tool_kind == "execute":
            if _matches_safe_prefix(command, settings.read_only_command_prefixes):
                return PolicyDecision("allow", "Review mode permits configured single-process read-only command")
            if _matches_safe_prefix(command, settings.safe_test_command_prefixes):
                return PolicyDecision("ask", "Test execution requires explicit approval")
        return PolicyDecision("deny", "Review mode blocks mutations")

    if mode is OrchestrationMode.execute:
        if not settings.allow_execute_mode:
            return PolicyDecision("deny", "Execute mode is disabled")
        if tool_kind in safe_non_mutating:
            return PolicyDecision("allow", "Read-only tool")
        if tool_kind in mutating:
            return PolicyDecision("ask", "File mutation requires approval")
        if tool_kind == "execute":
            if _matches_safe_prefix(command, settings.read_only_command_prefixes):
                return PolicyDecision("allow", "Configured single-process read-only command")
            return PolicyDecision("ask", "Command execution requires approval")
        return PolicyDecision("ask", f"Unclassified tool requires approval: {title}")

    return PolicyDecision("deny", "Unknown orchestration mode")
