from __future__ import annotations

import asyncio
import json
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from .acp_runtime import KimiAcpRuntime, KimiRuntimeError
from .audit import AuditLogger
from .config import Settings
from .models import (
    ConsensusRequest,
    ConsensusResult,
    EventType,
    GatewayEvent,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
    SubagentRequest,
)
from .prompting import build_task_prompt
from .providers import ProviderProfile, ProviderRegistry
from .security import redact_text, resolve_allowed_path, write_text_atomic
from .web_advisory import WebAdvisoryClient


class SessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditLogger(settings.audit_log)
        self.registry = ProviderRegistry.load(
            settings.provider_profiles_file,
            settings.routing_file,
        )
        self._apply_runtime_overrides()
        self.web = WebAdvisoryClient(settings.prompt_timeout_seconds)
        self.runtimes: dict[str, KimiAcpRuntime] = {}
        self.session_meta: dict[str, dict[str, Any]] = {}
        self.event_queues: dict[str, asyncio.Queue[GatewayEvent]] = {}
        self._stream_activity: dict[str, bool] = {}
        self._lock = asyncio.Lock()
        self._provider_locks = {
            profile.health_key(): asyncio.Semaphore(profile.max_concurrency)
            for profile in self.registry.profiles.values()
        }
        self._provider_start_locks = {
            profile.health_key(): asyncio.Lock() for profile in self.registry.profiles.values()
        }
        self._load_state()

    def _apply_runtime_overrides(self) -> None:
        secret_values = {
            "NVIDIA_API_KEY": self.settings.resolved_nvidia_api_key(),
            "KIMI_API_KEY": self.settings.resolved_kimi_api_key(),
            "DEEPSEEK_API_KEY": self.settings.resolved_deepseek_api_key(),
            "ZAI_API_KEY": self.settings.resolved_zai_api_key(),
            "K3_SELF_HOSTED_API_KEY": self.settings.resolved_k3_self_hosted_api_key(),
            "DS2API_API_KEY": self.settings.resolved_ds2api_api_key(),
            "DEEPSEEK_WEB_BRIDGE_KEY": self.settings.deepseek_web_bridge_key,
            "GLM_WEB_BRIDGE_KEY": self.settings.glm_web_bridge_key,
        }
        for profile in self.registry.profiles.values():
            if profile.api_key_env:
                profile.bind_api_key(secret_values.get(profile.api_key_env))

        ds2api = self.registry.profiles.get("ds2api-deepseek-v4-flash")
        if ds2api is not None:
            ds2api.base_url = self.settings.ds2api_base_url.rstrip("/")
            ds2api.enabled = self.settings.ds2api_enabled

        self_hosted = self.registry.profiles.get("kimi-k3-self-hosted")
        if self_hosted is not None:
            self_hosted.base_url = self.settings.k3_self_hosted_base_url.rstrip("/")
            self_hosted.enabled = self.settings.k3_self_hosted_enabled

        if not self.settings.mcp_internal_api_key.strip():
            self.settings.mcp_internal_api_key = secrets.token_urlsafe(32)

        mappings = {
            "deepseek-web-advisory": self.settings.deepseek_web_bridge_url,
            "glm-web-advisory": self.settings.glm_web_bridge_url,
        }
        for alias, url in mappings.items():
            profile = self.registry.profiles.get(alias)
            if profile is not None:
                profile.base_url = url.strip() or None
                profile.enabled = self.settings.enable_web_advisory_fallback and bool(url.strip())

    def _load_state(self) -> None:
        if not self.settings.state_file.exists():
            return
        try:
            payload = json.loads(self.settings.state_file.read_text(encoding="utf-8"))
            sessions = payload.get("sessions", {})
            if not isinstance(sessions, dict):
                return
            for external_id, value in sessions.items():
                if isinstance(value, str):
                    self.session_meta[str(external_id)] = {"kimi_session_id": value}
                elif isinstance(value, dict) and value.get("kimi_session_id"):
                    self.session_meta[str(external_id)] = value
        except (OSError, json.JSONDecodeError):
            self.session_meta = {}

    def _save_state(self) -> None:
        payload = {"version": 3, "sessions": self.session_meta}
        write_text_atomic(
            self.settings.state_file,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _resolve_workspace(self, cwd: str | None) -> Path:
        target = cwd or str(self.settings.default_workspace)
        return resolve_allowed_path(target, self.settings.workspace_roots())

    async def _emit(self, external_id: str, event: GatewayEvent) -> None:
        if event.event_type not in {EventType.status, EventType.usage}:
            stream_activity = getattr(self, "_stream_activity", None)
            if stream_activity is not None and external_id in stream_activity:
                stream_activity[external_id] = True
        queue = self.event_queues.get(external_id)
        if queue is not None:
            await queue.put(event)

    def _profile_for_existing(self, external_id: str) -> ProviderProfile | None:
        runtime = self.runtimes.get(external_id)
        if runtime is not None:
            return runtime.profile
        meta = self.session_meta.get(external_id, {})
        alias = meta.get("provider") or meta.get("model")
        return self.registry.profiles.get(str(alias)) if alias else None

    def _candidate_profiles(self, request: OrchestrationRequest) -> list[ProviderProfile]:
        existing = self._profile_for_existing(request.session_id) if request.session_id else None
        if existing is not None:
            return [existing]
        if request.model and request.model != "multi-agent-orchestrator":
            profile = self.registry.get(request.model)
            state = self.registry.state_for(profile.alias)
            circuit_blocked = state.permanently_disabled or state.open_until > time.time()
            if (not profile.available() or circuit_blocked) and not request.allow_fallback:
                reason = "circuit is open" if circuit_blocked else (
                    f"configure {profile.api_key_env or 'its login'}"
                )
                raise KimiRuntimeError(f"Provider {profile.alias} is not available; {reason}")
            if request.allow_fallback:
                tail = self.registry.candidates(request.role, request.preferred_models or None)
                # DeepSeek Flash has a provider-specific emergency path. Keep it
                # adjacent to the explicit NVIDIA choice even when callers omit
                # the `fast`/`coder` role and use the default orchestrator role.
                if profile.alias == "nvidia-deepseek-v4-flash" and not request.preferred_models:
                    tail = [*self.registry.candidates("fast"), *tail]
                seen = {profile.health_key()}
                ordered_tail = []
                for item in tail:
                    if item.health_key() not in seen:
                        seen.add(item.health_key())
                        ordered_tail.append(item)
                if profile.available() and not circuit_blocked:
                    return [profile, *ordered_tail]
                if ordered_tail:
                    return ordered_tail
                raise KimiRuntimeError(
                    f"Provider {profile.alias} is not available and no fallback provider is ready"
                )
            if not profile.available():
                raise KimiRuntimeError(
                    f"Provider {profile.alias} is not available; configure {profile.api_key_env or 'its login'}"
                )
            return [profile]
        preferred = request.preferred_models or None
        profiles = self.registry.candidates(request.role or self.settings.default_role, preferred)
        if not profiles:
            raise KimiRuntimeError(
                f"No available providers for role {request.role}. Configure Kimi OAuth or an API key."
            )
        return profiles

    def _validate_existing_request(
        self,
        external_id: str,
        runtime: KimiAcpRuntime,
        request: OrchestrationRequest,
        profile: ProviderProfile,
    ) -> None:
        requested_workspace = runtime.workspace if request.cwd is None else self._resolve_workspace(request.cwd)
        if requested_workspace != runtime.workspace:
            raise KimiRuntimeError(
                f"Session {external_id} is bound to {runtime.workspace}; start a new session for {requested_workspace}"
            )
        if profile.alias != runtime.profile.alias:
            raise KimiRuntimeError("Changing provider/model inside a live session is disabled")
        requested_thinking = request.thinking or runtime.thinking
        if requested_thinking != runtime.thinking:
            raise KimiRuntimeError("Changing reasoning effort inside a live session is disabled")

    def _self_mcp_server(self) -> dict[str, Any]:
        project_root = Path(__file__).resolve().parents[1]
        python_cmd = self.settings.self_mcp_python.strip() or sys.executable
        env = {
            "PYTHONPATH": str(project_root),
            "GATEWAY_HOST": self.settings.gateway_host,
            "GATEWAY_PORT": str(self.settings.gateway_port),
            "MCP_INTERNAL_API_KEY": self.settings.resolved_mcp_internal_api_key(),
        }
        return {
            "name": "multi-model-orchestrator",
            "command": python_cmd,
            "args": ["-m", "app.mcp_server"],
            "env": env,
            "cwd": str(project_root),
        }

    def _mcp_servers_for(self, request: OrchestrationRequest) -> list[dict[str, Any]]:
        servers = list(request.mcp_servers)
        enable = request.enable_self_mcp
        if enable is None:
            enable = self.settings.enable_self_mcp and request.role == "orchestrator"
        if enable and not any(str(item.get("name")) == "multi-model-orchestrator" for item in servers):
            servers.append(self._self_mcp_server())
        return servers

    async def _respect_min_interval(self, profile: ProviderProfile) -> None:
        if profile.min_interval_seconds <= 0:
            return
        lock = self._provider_start_locks[profile.health_key()]
        async with lock:
            state = self.registry.state_for(profile.alias)
            wait = profile.min_interval_seconds - (time.time() - state.last_started_at)
            if wait > 0:
                await asyncio.sleep(wait)
            state.last_started_at = time.time()

    async def _get_or_create_runtime(
        self,
        request: OrchestrationRequest,
        profile: ProviderProfile,
        external_id: str,
    ) -> KimiAcpRuntime:
        existing = self.runtimes.get(external_id)
        if existing is not None:
            self._validate_existing_request(external_id, existing, request, profile)
            await existing.configure_mode(request.mode)
            return existing

        async with self._lock:
            existing = self.runtimes.get(external_id)
            if existing is not None:
                self._validate_existing_request(external_id, existing, request, profile)
                await existing.configure_mode(request.mode)
                return existing
            await self._evict_if_needed()
            meta = self.session_meta.get(external_id, {})
            workspace_hint = request.cwd or meta.get("workspace")
            workspace = self._resolve_workspace(workspace_hint)
            additional = [
                resolve_allowed_path(path, self.settings.workspace_roots())
                for path in request.additional_directories
            ]
            thinking = request.thinking or profile.default_thinking or self.settings.default_thinking
            runtime = KimiAcpRuntime(
                self.settings,
                self.audit,
                workspace=workspace,
                mode=request.mode,
                profile=profile,
                thinking=thinking,
                additional_directories=additional,
                mcp_servers=self._mcp_servers_for(request),
                event_callback=lambda event: self._emit(external_id, event),
            )
            stored_workspace = meta.get("workspace")
            if stored_workspace and Path(stored_workspace).expanduser().resolve() != workspace:
                raise KimiRuntimeError(
                    f"Persisted session {external_id} belongs to {stored_workspace}, not {workspace}"
                )
            stored_provider = meta.get("provider") or meta.get("model")
            if stored_provider and stored_provider != profile.alias:
                raise KimiRuntimeError(
                    f"Persisted session {external_id} uses {stored_provider}; start a new session for {profile.alias}"
                )
            kimi_session = meta.get("kimi_session_id")
            started_session = await runtime.start(str(kimi_session) if kimi_session else None)
            self.runtimes[external_id] = runtime
            self.session_meta[external_id] = {
                "kimi_session_id": started_session,
                "workspace": str(workspace),
                "provider": profile.alias,
                "runtime_model": profile.model,
                "thinking": thinking,
                "role": request.role,
                "updated_at": time.time(),
            }
            self._save_state()
            return runtime

    async def _evict_if_needed(self) -> None:
        now = time.time()
        stale = [
            key
            for key, runtime in self.runtimes.items()
            if now - runtime.last_used_at > self.settings.session_idle_ttl_seconds
            and not runtime.lock.locked()
        ]
        for key in stale:
            runtime = self.runtimes.pop(key)
            await runtime.close()
        while len(self.runtimes) >= self.settings.max_live_sessions:
            candidates = [item for item in self.runtimes.items() if not item[1].lock.locked()]
            if not candidates:
                raise KimiRuntimeError("All agent sessions are currently busy")
            key, runtime = min(candidates, key=lambda item: item[1].last_used_at)
            self.runtimes.pop(key)
            await runtime.close()

    async def _run_profile(
        self,
        request: OrchestrationRequest,
        profile: ProviderProfile,
        task_prompt: str,
        external_id: str,
    ) -> OrchestrationResult:
        if profile.advisory_only and request.mode in {OrchestrationMode.execute, OrchestrationMode.yolo}:
            raise KimiRuntimeError(f"{profile.alias} is advisory-only")
        semaphore = self._provider_locks[profile.health_key()]
        async with semaphore:
            await self._respect_min_interval(profile)
            if profile.transport == "web":
                text = await self.web.chat(profile, task_prompt, request.mode)
                if not text.strip():
                    raise KimiRuntimeError(f"Provider {profile.alias} returned an empty response")
                event = GatewayEvent(
                    event_type=EventType.status,
                    timestamp=time.time(),
                    payload={"transport": "web_advisory", "provider": profile.alias},
                )
                return OrchestrationResult(
                    session_id=external_id,
                    text=text,
                    stop_reason="end_turn",
                    mode=request.mode,
                    model=profile.alias,
                    provider=profile.alias,
                    role=request.role,
                    events=[event],
                )
            runtime = await self._get_or_create_runtime(request, profile, external_id)
            text, stop_reason, usage = await runtime.prompt(task_prompt)
            reasoning_content = "".join(runtime.thought_parts)
            tool_calls = list(runtime.tool_calls.values())
            if not text.strip() and not reasoning_content.strip() and not tool_calls:
                raise KimiRuntimeError(f"Provider {profile.alias} returned an empty response")
            meta = self.session_meta.get(external_id)
            if meta is not None:
                meta["updated_at"] = time.time()
                self._save_state()
            return OrchestrationResult(
                session_id=external_id,
                text=text,
                stop_reason=stop_reason,
                mode=request.mode,
                model=profile.alias,
                provider=profile.alias,
                role=request.role,
                upstream_model=profile.model,
                reasoning_content=reasoning_content or None,
                tool_calls=tool_calls,
                events=list(runtime.events),
                usage=usage,
            )

    async def run(self, request: OrchestrationRequest, *, external_id: str | None = None) -> OrchestrationResult:
        task_prompt = build_task_prompt(request.prompt, request.mode, request.system, role=request.role)
        external_id = external_id or request.session_id or uuid.uuid4().hex
        attempts: list[dict[str, Any]] = []
        candidates = self._candidate_profiles(request)
        candidates = candidates[: self.settings.max_route_attempts]
        last_error: Exception | None = None
        for index, profile in enumerate(candidates):
            if index > 0 and (request.session_id or not request.allow_fallback):
                break
            retried_rate_limit = False
            while len(attempts) < self.settings.max_route_attempts:
                started = time.time()
                try:
                    result = await self._run_profile(request, profile, task_prompt, external_id)
                    self.registry.record_success(profile.alias)
                    attempts.append({
                        "provider": profile.alias,
                        "upstream_model": profile.model,
                        "status": "success",
                        "elapsed": time.time() - started,
                    })
                    result.attempts = attempts
                    return result
                except Exception as exc:
                    last_error = exc
                    kind = self.registry.record_failure(profile.alias, exc)
                    attempts.append(
                        {
                            "provider": profile.alias,
                            "upstream_model": profile.model,
                            "status": "failed",
                            "error": redact_text(str(exc)),
                            "failure_kind": kind,
                            "elapsed": time.time() - started,
                        }
                    )
                    self.audit.write(
                        "provider_attempt_failed",
                        external_session_id=external_id,
                        provider=profile.alias,
                        role=request.role,
                        error=redact_text(str(exc)),
                        failure_kind=kind,
                    )
                    runtime = self.runtimes.pop(external_id, None)
                    if runtime is not None:
                        await runtime.close()
                    if request.session_id is None:
                        self.session_meta.pop(external_id, None)
                        self._save_state()
                    # Once a streaming provider has emitted content or a tool
                    # event, switching providers would concatenate two partial
                    # responses that the client cannot roll back. Only a
                    # failure before stream activity may fail over safely.
                    if getattr(self, "_stream_activity", {}).get(external_id, False):
                        break
                    if kind == "rate_limit" and not retried_rate_limit and len(attempts) < self.settings.max_route_attempts:
                        retried_rate_limit = True
                        await asyncio.sleep(self.registry.retry_after_seconds(exc))
                        continue
                    if request.session_id or not request.allow_fallback:
                        break
                    break
            if getattr(self, "_stream_activity", {}).get(external_id, False):
                break
        raise KimiRuntimeError(
            f"All provider routes failed for role {request.role}: {redact_text(str(last_error))}; attempts={attempts}"
        )

    async def dispatch_subagent(self, request: SubagentRequest) -> OrchestrationResult:
        orchestration = OrchestrationRequest(
            prompt=request.prompt,
            cwd=request.cwd,
            mode=request.mode,
            model=request.model,
            role=request.role,
            thinking=request.thinking,
            system=request.system,
            allow_fallback=request.allow_fallback,
            preferred_models=request.preferred_models,
            enable_self_mcp=False,
        )
        return await self.run(orchestration)

    async def consensus(self, request: ConsensusRequest) -> ConsensusResult:
        limit = min(request.max_parallel or self.settings.max_parallel_subagents, self.settings.max_parallel_subagents)
        semaphore = asyncio.Semaphore(limit)

        async def one(role: str, model: str | None) -> OrchestrationResult:
            async with semaphore:
                return await self.dispatch_subagent(
                    SubagentRequest(
                        prompt=request.prompt,
                        cwd=request.cwd,
                        role=role,
                        mode=request.mode,
                        model=model,
                        thinking=request.thinking,
                        allow_fallback=True,
                    )
                )

        jobs = []
        for index, role in enumerate(request.roles):
            model = request.models[index] if index < len(request.models) else None
            jobs.append(one(role, model))
        responses = await asyncio.gather(*jobs, return_exceptions=True)
        good: list[OrchestrationResult] = []
        for role, result in zip(request.roles, responses):
            if isinstance(result, Exception):
                good.append(
                    OrchestrationResult(
                        session_id=uuid.uuid4().hex,
                        text=f"Subagent {role} failed: {redact_text(str(result))}",
                        stop_reason="error",
                        mode=request.mode,
                        model="unavailable",
                        provider="unavailable",
                        role=role,
                        attempts=[{"status": "failed", "error": redact_text(str(result))}],
                    )
                )
            else:
                good.append(result)

        synthesis: OrchestrationResult | None = None
        if request.synthesize:
            joined = "\n\n".join(
                f"## {item.role} via {item.provider}\n{item.text}" for item in good
            )
            synthesis = await self.run(
                OrchestrationRequest(
                    prompt=(
                        "Synthesize the independent subagent reports below. Resolve disagreements, "
                        "identify evidence, and produce one actionable recommendation.\n\n" + joined
                    ),
                    cwd=request.cwd,
                    mode=OrchestrationMode.review,
                    role="orchestrator",
                    allow_fallback=True,
                    enable_self_mcp=False,
                )
            )
        return ConsensusResult(responses=good, synthesis=synthesis)

    async def stream(self, request: OrchestrationRequest) -> AsyncIterator[GatewayEvent]:
        external_id = request.session_id or uuid.uuid4().hex
        queue: asyncio.Queue[GatewayEvent] = asyncio.Queue()
        self.event_queues[external_id] = queue
        stream_activity = getattr(self, "_stream_activity", None)
        if stream_activity is None:
            self._stream_activity = {}
        self._stream_activity[external_id] = False

        async def runner() -> None:
            try:
                result = await self.run(request, external_id=external_id)
                await queue.put(
                    GatewayEvent(
                        event_type=EventType.status,
                        timestamp=time.time(),
                        payload={
                            "state": "completed",
                            "session_id": result.session_id,
                            "text": result.text,
                            "stop_reason": result.stop_reason,
                            "usage": result.usage,
                            "provider": result.provider,
                            "upstream_model": result.upstream_model,
                            "attempts": result.attempts,
                            "reasoning_content": result.reasoning_content,
                            "tool_calls": result.tool_calls,
                        },
                    )
                )
            except Exception as exc:
                await queue.put(
                    GatewayEvent(
                        event_type=EventType.error,
                        timestamp=time.time(),
                        payload={"message": redact_text(str(exc))},
                    )
                )

        task = asyncio.create_task(runner())
        try:
            while True:
                event = await queue.get()
                yield event
                if event.event_type is EventType.error or (
                    event.event_type is EventType.status and event.payload.get("state") == "completed"
                ):
                    break
        finally:
            self.event_queues.pop(external_id, None)
            self._stream_activity.pop(external_id, None)
            if not task.done():
                task.cancel()

    async def approvals(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for external_id, runtime in self.runtimes.items():
            for record, _, _ in runtime.pending_approvals.values():
                payload = record.model_dump()
                payload["external_session_id"] = external_id
                payload["provider"] = runtime.profile.alias
                output.append(payload)
        return output

    async def resolve_approval(self, approval_id: str, approve: bool, always: bool) -> bool:
        for runtime in self.runtimes.values():
            if await runtime.resolve_approval(approval_id, approve=approve, always=always):
                return True
        return False

    async def cancel(self, external_id: str) -> bool:
        runtime = self.runtimes.get(external_id)
        if runtime is None:
            return False
        await runtime.cancel()
        return True

    async def close_session(self, external_id: str, *, forget: bool = False) -> bool:
        runtime = self.runtimes.pop(external_id, None)
        if runtime is not None:
            await runtime.close()
        exists = runtime is not None or external_id in self.session_meta
        if forget:
            self.session_meta.pop(external_id, None)
            self._save_state()
        return exists

    def sessions(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for external_id, meta in self.session_meta.items():
            runtime = self.runtimes.get(external_id)
            output.append(
                {
                    "session_id": external_id,
                    **meta,
                    "live": runtime is not None,
                    "busy": runtime.lock.locked() if runtime else False,
                    "mode": runtime.mode.value if runtime else None,
                }
            )
        return sorted(output, key=lambda item: float(item.get("updated_at", 0)), reverse=True)

    async def close(self) -> None:
        runtimes = list(self.runtimes.values())
        self.runtimes.clear()
        await asyncio.gather(*(runtime.close() for runtime in runtimes), return_exceptions=True)
