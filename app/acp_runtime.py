from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Awaitable, Callable

from .audit import AuditLogger
from .config import Settings
from .models import ApprovalRecord, EventType, GatewayEvent, OrchestrationMode
from .policy import decide_permission
from .providers import ProviderProfile
from .security import PathSecurityError, resolve_allowed_path

EventCallback = Callable[[GatewayEvent], Awaitable[None]]


class KimiRuntimeError(RuntimeError):
    pass


class KimiNotInstalled(KimiRuntimeError):
    pass


class KimiApprovalTimeout(KimiRuntimeError):
    pass


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, value.get(_snake_to_camel(name), default))
    return getattr(value, name, default)


def _snake_to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


def _text_from_content_block(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text", "")) if content.get("type") == "text" else ""
    if getattr(content, "type", None) == "text":
        return str(getattr(content, "text", ""))
    return ""


class RuntimeClient:
    """ACP client callbacks used by the Kimi Code agent subprocess."""

    def __init__(
        self,
        runtime: "KimiAcpRuntime",
        settings: Settings,
        audit: AuditLogger,
    ) -> None:
        self.runtime = runtime
        self.settings = settings
        self.audit = audit
        self.connection: Any = None

    def on_connect(self, conn: Any) -> None:
        self.connection = conn

    async def session_update(self, session_id: str, update: Any, **_: Any) -> None:
        payload = _dump(update)
        update_type = str(
            _field(update, "session_update", payload.get("sessionUpdate", "status"))
        )
        mapping = {
            "agent_message_chunk": EventType.message,
            "agent_thought_chunk": EventType.thought,
            "plan": EventType.plan,
            "plan_update": EventType.plan,
            "tool_call": EventType.tool,
            "tool_call_update": EventType.tool,
            "usage_update": EventType.usage,
        }
        event_type = mapping.get(update_type, EventType.status)
        event = GatewayEvent(event_type=event_type, timestamp=time.time(), payload=payload)
        await self.runtime.record_event(event)

        if update_type == "agent_message_chunk":
            content = _field(update, "content")
            text = _text_from_content_block(content)
            if text:
                self.runtime.answer_parts.append(text)
        elif update_type == "agent_thought_chunk":
            content = _field(update, "content")
            text = _text_from_content_block(content)
            if text:
                self.runtime.thought_parts.append(text)
        elif update_type in {"tool_call", "tool_call_update"}:
            tool_call_id = str(_field(update, "tool_call_id", ""))
            if tool_call_id:
                current = self.runtime.tool_calls.setdefault(tool_call_id, {})
                current.update(payload)

    async def request_permission(
        self,
        session_id: str,
        tool_call: Any,
        options: list[Any],
        **_: Any,
    ) -> dict[str, Any]:
        tool_payload = _dump(tool_call)
        title = str(_field(tool_call, "title", "Tool request"))
        kind = _field(tool_call, "kind")
        raw_input = _field(tool_call, "raw_input")
        tool_call_id = _field(tool_call, "tool_call_id")
        option_payloads = [_dump(option) for option in options]
        decision = decide_permission(self.runtime.mode, kind, title, raw_input, self.settings)
        self.audit.write(
            "permission_decision",
            session_id=session_id,
            mode=self.runtime.mode.value,
            action=decision.action,
            reason=decision.reason,
            tool=tool_payload,
        )

        if decision.action == "allow":
            if str(kind or "").lower() in {"edit", "delete", "move"}:
                self.runtime.grant_file_write(raw_input)
            option_id = _select_option(options, allow=True, always=False)
            if option_id:
                return {"outcome": {"outcome": "selected", "optionId": option_id}}
            return {"outcome": {"outcome": "cancelled"}}
        if decision.action == "deny":
            option_id = _select_option(options, allow=False, always=False)
            if option_id:
                return {"outcome": {"outcome": "selected", "optionId": option_id}}
            return {"outcome": {"outcome": "cancelled"}}

        approval_id = uuid.uuid4().hex
        record = ApprovalRecord(
            approval_id=approval_id,
            session_id=session_id,
            tool_call_id=str(tool_call_id) if tool_call_id else None,
            title=title,
            kind=str(kind) if kind else None,
            raw_input=raw_input,
            options=option_payloads,
            created_at=time.time(),
        )
        future: asyncio.Future[tuple[bool, bool]] = asyncio.get_running_loop().create_future()
        self.runtime.pending_approvals[approval_id] = (record, future, options)
        await self.runtime.record_event(
            GatewayEvent(
                event_type=EventType.approval,
                timestamp=time.time(),
                payload=record.model_dump(),
            )
        )
        try:
            approve, always = await asyncio.wait_for(
                future, timeout=self.settings.approval_timeout_seconds
            )
        except TimeoutError as exc:
            record.status = "expired"
            record.resolved_at = time.time()
            raise KimiApprovalTimeout(f"Approval timed out: {title}") from exc
        finally:
            self.runtime.pending_approvals.pop(approval_id, None)

        option_id = _select_option(options, allow=approve, always=always)
        if approve and str(kind or "").lower() in {"edit", "delete", "move"}:
            self.runtime.grant_file_write(raw_input)
        record.status = "approved" if approve else "rejected"
        record.selected_option_id = option_id
        record.resolved_at = time.time()
        if option_id:
            return {"outcome": {"outcome": "selected", "optionId": option_id}}
        return {"outcome": {"outcome": "cancelled"}}

    async def read_text_file(
        self,
        session_id: str,
        path: str,
        line: int | None = None,
        limit: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        resolved = resolve_allowed_path(path, self.runtime.workspace_roots, must_exist=True)
        text = resolved.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        start = max((line or 1) - 1, 0)
        stop = start + limit if limit is not None else None
        return {"content": "".join(lines[start:stop])}

    async def write_text_file(
        self,
        session_id: str,
        path: str,
        content: str,
        **_: Any,
    ) -> dict[str, Any]:
        resolved = resolve_allowed_path(path, self.runtime.workspace_roots)
        if self.runtime.mode not in {OrchestrationMode.execute, OrchestrationMode.yolo}:
            raise PathSecurityError("Current mode does not permit file writes")
        if self.runtime.mode is not OrchestrationMode.yolo and not self.runtime.consume_file_write_grant(resolved):
            raise PathSecurityError("File write has no matching one-time approval grant")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        self.audit.write("file_write", session_id=session_id, path=str(resolved), size=len(content))
        return {}

    async def create_terminal(self, *args: Any, **kwargs: Any) -> Any:
        raise KimiRuntimeError("ACP terminal reverse-RPC is not enabled by Kimi Code")

    async def terminal_output(self, *args: Any, **kwargs: Any) -> Any:
        raise KimiRuntimeError("ACP terminal reverse-RPC is not enabled by Kimi Code")

    async def release_terminal(self, *args: Any, **kwargs: Any) -> Any:
        return {}

    async def wait_for_terminal_exit(self, *args: Any, **kwargs: Any) -> Any:
        raise KimiRuntimeError("ACP terminal reverse-RPC is not enabled by Kimi Code")

    async def kill_terminal(self, *args: Any, **kwargs: Any) -> Any:
        return {}

    async def create_elicitation(self, message: str, mode: Any, **_: Any) -> dict[str, Any]:
        self.audit.write("elicitation_rejected", message=message, mode=str(mode))
        return {"action": "cancel"}

    async def complete_elicitation(self, elicitation_id: str, **_: Any) -> None:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise KimiRuntimeError(f"Unsupported ACP extension method: {method}")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        self.audit.write("acp_extension_notification", method=method, params=params)


def _select_option(options: list[Any], *, allow: bool, always: bool) -> str | None:
    preferred = []
    if allow:
        preferred = ["allow_always", "allow_once"] if always else ["allow_once", "allow_always"]
    else:
        preferred = ["reject_always", "reject_once"] if always else ["reject_once", "reject_always"]
    for kind in preferred:
        for option in options:
            if str(_field(option, "kind", "")) == kind:
                return str(_field(option, "option_id"))
    return None


class KimiAcpRuntime:
    def __init__(
        self,
        settings: Settings,
        audit: AuditLogger,
        *,
        workspace: Path,
        mode: OrchestrationMode,
        profile: ProviderProfile,
        thinking: str,
        additional_directories: list[Path] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        event_callback: EventCallback | None = None,
    ) -> None:
        self.settings = settings
        self.audit = audit
        self.workspace = workspace.resolve()
        self.workspace_roots = [self.workspace, *(additional_directories or [])]
        self.mode = mode
        self.profile = profile
        self.model = profile.alias
        self.runtime_model = profile.model
        self.thinking = thinking
        self.mcp_servers = mcp_servers or []
        self.event_callback = event_callback

        self.client = RuntimeClient(self, settings, audit)
        self.conn: Any = None
        self.process: Any = None
        self.session_id: str | None = None
        self.context: AbstractAsyncContextManager[Any] | None = None
        self.events: list[GatewayEvent] = []
        self.answer_parts: list[str] = []
        self.thought_parts: list[str] = []
        self.tool_calls: dict[str, dict[str, Any]] = {}
        self.pending_approvals: dict[
            str, tuple[ApprovalRecord, asyncio.Future[tuple[bool, bool]], list[Any]]
        ] = {}
        self.lock = asyncio.Lock()
        self.last_used_at = time.time()
        self.file_write_grants: dict[Path, int] = {}
        self.unscoped_write_grants = 0
        self.option_ids: dict[str, str] = {}

    def grant_file_write(self, raw_input: Any) -> None:
        paths: list[str] = []

        def collect(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for child_key, child in value.items():
                    collect(child, str(child_key).lower())
            elif isinstance(value, list):
                for child in value:
                    collect(child, key)
            elif isinstance(value, str) and key in {
                "path", "file", "file_path", "filepath", "destination", "dest", "target", "source"
            }:
                paths.append(value)

        collect(raw_input)
        granted = 0
        for value in paths:
            try:
                resolved = resolve_allowed_path(value, self.workspace_roots)
            except (PathSecurityError, OSError):
                continue
            self.file_write_grants[resolved] = self.file_write_grants.get(resolved, 0) + 1
            granted += 1
        if granted == 0:
            # Some ACP edit requests omit a path. Allow exactly one subsequent write,
            # rather than opening the whole workspace for a time window.
            self.unscoped_write_grants += 1

    def consume_file_write_grant(self, path: Path) -> bool:
        remaining = self.file_write_grants.get(path, 0)
        if remaining > 0:
            if remaining == 1:
                self.file_write_grants.pop(path, None)
            else:
                self.file_write_grants[path] = remaining - 1
            return True
        if self.unscoped_write_grants > 0:
            self.unscoped_write_grants -= 1
            return True
        return False

    async def record_event(self, event: GatewayEvent) -> None:
        self.events.append(event)
        if self.event_callback is not None:
            await self.event_callback(event)

    async def start(self, existing_session_id: str | None = None) -> str:
        executable = shutil.which(self.settings.kimi_command)
        if executable is None:
            raise KimiNotInstalled(
                f"Kimi Code command not found: {self.settings.kimi_command}. Install Kimi Code first."
            )
        try:
            from acp import PROTOCOL_VERSION, spawn_agent_process
        except ImportError as exc:
            raise KimiRuntimeError(
                "Missing dependency 'agent-client-protocol'. Run the setup script."
            ) from exc

        blocked = {
            "NVIDIA_API_KEY", "DEEPSEEK_API_KEY", "ZAI_API_KEY",
            "DS2API_API_KEY",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "KIMI_API_KEY",
            "GATEWAY_API_KEY", "MCP_INTERNAL_API_KEY",
            "DEEPSEEK_WEB_BRIDGE_KEY", "GLM_WEB_BRIDGE_KEY",
        }
        env = {
            key: value for key, value in os.environ.items()
            if key not in blocked and not key.startswith("KIMI_MODEL_")
        }
        if self.profile.transport == "oauth":
            runtime_home = self.settings.kimi_code_home
        else:
            safe_alias = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in self.profile.alias)
            runtime_home = self.settings.kimi_code_home / "providers" / safe_alias
        runtime_home.mkdir(parents=True, exist_ok=True)
        env["KIMI_CODE_HOME"] = str(runtime_home.resolve())
        env["KIMI_DISABLE_TELEMETRY"] = "1"
        env["KIMI_CODE_AGENT_SWARM_MAX_CONCURRENCY"] = str(self.settings.max_parallel_subagents)
        env["KIMI_SUBAGENT_TIMEOUT_MS"] = str(int(self.settings.prompt_timeout_seconds * 1000))
        env.update(self.profile.kimi_environment(self.thinking))
        self.context = spawn_agent_process(
            self.client,
            executable,
            "acp",
            env=env,
            cwd=str(self.workspace),
        )
        self.conn, self.process = await self.context.__aenter__()
        await self.conn.initialize(protocol_version=PROTOCOL_VERSION)
        if existing_session_id:
            try:
                response = await self.conn.resume_session(
                    session_id=existing_session_id,
                    cwd=str(self.workspace),
                    additional_directories=[str(path) for path in self.workspace_roots[1:]],
                    mcp_servers=self.mcp_servers,
                )
                self.session_id = existing_session_id
            except Exception:
                response = await self.conn.load_session(
                    session_id=existing_session_id,
                    cwd=str(self.workspace),
                    additional_directories=[str(path) for path in self.workspace_roots[1:]],
                    mcp_servers=self.mcp_servers,
                )
                self.session_id = existing_session_id
        else:
            response = await self.conn.new_session(
                cwd=str(self.workspace),
                additional_directories=[str(path) for path in self.workspace_roots[1:]],
                mcp_servers=self.mcp_servers,
            )
            self.session_id = str(_field(response, "session_id"))

        await self._set_option(response, category="model", fallback_ids=("model",), value=self.runtime_model)
        await self._set_option(
            response,
            category="thought_level",
            fallback_ids=("thinking", "reasoning_effort", "thought_level"),
            value=self.thinking,
        )
        mode_value = {
            OrchestrationMode.plan: "plan",
            OrchestrationMode.review: "default",
            OrchestrationMode.execute: "default",
            OrchestrationMode.yolo: "yolo",
        }[self.mode]
        await self._set_option(
            response,
            category="mode",
            fallback_ids=("mode",),
            value=mode_value,
        )
        self.audit.write(
            "runtime_started",
            session_id=self.session_id,
            workspace=str(self.workspace),
            mode=self.mode.value,
            model=self.model,
            runtime_model=self.runtime_model,
            provider_transport=self.profile.transport,
            runtime_home=str(runtime_home.resolve()),
        )
        return self.session_id

    async def _set_option(
        self,
        response: Any,
        *,
        category: str,
        fallback_ids: tuple[str, ...],
        value: str,
    ) -> None:
        options = _field(response, "config_options", []) or []
        selected_id: str | None = None
        for option in options:
            option_id = str(_field(option, "id", ""))
            option_category = _field(option, "category")
            if option_category == category or option_id in fallback_ids:
                selected_id = option_id
                break
        if selected_id:
            self.option_ids[category] = selected_id
        if selected_id and self.conn is not None:
            try:
                await self.conn.set_config_option(
                    session_id=self.session_id,
                    config_id=selected_id,
                    value=value,
                )
            except Exception as exc:
                self.audit.write(
                    "config_option_failed",
                    session_id=self.session_id,
                    config_id=selected_id,
                    value=value,
                    error=str(exc),
                )

    async def configure_mode(self, mode: OrchestrationMode) -> None:
        """Update only the orchestration mode on a live session.

        Model and thinking changes intentionally require a new external session because
        Kimi documents that switching either invalidates the context cache.
        """
        self.mode = mode
        if self.conn is None or self.session_id is None:
            return
        config_id = self.option_ids.get("mode")
        if config_id:
            value = {
                OrchestrationMode.plan: "plan",
                OrchestrationMode.review: "default",
                OrchestrationMode.execute: "default",
                OrchestrationMode.yolo: "yolo",
            }[mode]
            try:
                await self.conn.set_config_option(
                    session_id=self.session_id,
                    config_id=config_id,
                    value=value,
                )
            except Exception as exc:
                self.audit.write(
                    "mode_config_failed",
                    session_id=self.session_id,
                    mode=mode.value,
                    error=str(exc),
                )

    async def prompt(self, text: str) -> tuple[str, str, dict[str, Any] | None]:
        if self.conn is None or self.session_id is None:
            raise KimiRuntimeError("Runtime has not been started")
        try:
            from acp import text_block
        except ImportError as exc:
            raise KimiRuntimeError("Missing ACP SDK") from exc
        async with self.lock:
            self.answer_parts.clear()
            self.thought_parts.clear()
            self.tool_calls.clear()
            self.events.clear()
            response = await asyncio.wait_for(
                self.conn.prompt(session_id=self.session_id, prompt=[text_block(text)]),
                timeout=self.settings.prompt_timeout_seconds,
            )
            self.last_used_at = time.time()
            self.file_write_grants.clear()
            self.unscoped_write_grants = 0
            stop_reason = str(_field(response, "stop_reason", "end_turn"))
            usage = _dump(_field(response, "usage")) if _field(response, "usage") else None
            return "".join(self.answer_parts), stop_reason, usage

    async def resolve_approval(self, approval_id: str, *, approve: bool, always: bool) -> bool:
        pending = self.pending_approvals.get(approval_id)
        if pending is None:
            return False
        _, future, _ = pending
        if not future.done():
            future.set_result((approve, always))
        return True

    async def cancel(self) -> None:
        if self.conn is not None and self.session_id is not None:
            await self.conn.cancel(session_id=self.session_id)

    async def close(self) -> None:
        if self.context is not None:
            await self.context.__aexit__(None, None, None)
            self.context = None
            self.conn = None
            self.process = None
        self.audit.write("runtime_closed", session_id=self.session_id)
