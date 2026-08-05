from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class OrchestrationMode(str, Enum):
    plan = "plan"
    review = "review"
    execute = "execute"
    yolo = "yolo"


class EventType(str, Enum):
    message = "message"
    thought = "thought"
    plan = "plan"
    tool = "tool"
    approval = "approval"
    usage = "usage"
    status = "status"
    error = "error"


class GatewayEvent(BaseModel):
    event_type: EventType
    timestamp: float
    payload: dict[str, Any]


class ApprovalRecord(BaseModel):
    approval_id: str
    session_id: str
    tool_call_id: str | None = None
    title: str
    kind: str | None = None
    raw_input: Any = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    selected_option_id: str | None = None
    created_at: float
    resolved_at: float | None = None


class OrchestrationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    cwd: str | None = None
    mode: OrchestrationMode = OrchestrationMode.plan
    model: str | None = None
    role: str = "orchestrator"
    thinking: str | None = None
    session_id: str | None = None
    additional_directories: list[str] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    system: str | None = None
    allow_fallback: bool = True
    preferred_models: list[str] = Field(default_factory=list)
    enable_self_mcp: bool | None = None


class OrchestrationResult(BaseModel):
    session_id: str
    text: str
    stop_reason: str
    mode: OrchestrationMode
    model: str
    provider: str
    role: str
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    events: list[GatewayEvent] = Field(default_factory=list)
    usage: dict[str, Any] | None = None


class SubagentRequest(BaseModel):
    prompt: str = Field(min_length=1)
    cwd: str
    role: str = "reviewer"
    mode: OrchestrationMode = OrchestrationMode.review
    model: str | None = None
    thinking: str | None = None
    system: str | None = None
    preferred_models: list[str] = Field(default_factory=list)
    allow_fallback: bool = True


class ConsensusRequest(BaseModel):
    prompt: str = Field(min_length=1)
    cwd: str
    roles: list[str] = Field(default_factory=lambda: ["architect", "reviewer"])
    models: list[str] = Field(default_factory=list)
    mode: OrchestrationMode = OrchestrationMode.review
    thinking: str | None = None
    max_parallel: int | None = None
    synthesize: bool = True


class ConsensusResult(BaseModel):
    responses: list[OrchestrationResult]
    synthesis: OrchestrationResult | None = None


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str = "multi-agent-orchestrator"
    messages: list[ChatMessage]
    stream: bool = False
    metadata: dict[str, Any] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None


class ApprovalResolution(BaseModel):
    approve: bool
    always: bool = False
