from __future__ import annotations

from typing import Any

from .models import OrchestrationMode


MODE_INSTRUCTIONS = {
    OrchestrationMode.plan: """
Operate in architecture/plan mode. Inspect the workspace, identify risks and dependencies, and produce a concrete implementation plan. Do not edit files or execute mutating commands. Use built-in explore/plan/coder subagents and the multi-model MCP workers where useful.
""",
    OrchestrationMode.review: """
Operate in review mode. Inspect existing code and diffs, run only approved non-mutating checks, identify correctness/security/maintainability issues, and propose exact fixes. Do not modify files. Ask independent model workers for criticism when uncertainty is material.
""",
    OrchestrationMode.execute: """
Operate as the main engineering orchestrator. Follow a plan → implement → test → review → repair loop, with independent review before completion. All built-in subagents are allowed. Use external DeepSeek/GLM workers for parallel analysis and review, but keep actual workspace mutation under this controlled session. Ask for permission before file mutations or shell commands when the client requires it. Preserve user work and report validation evidence.
""",
    OrchestrationMode.yolo: """
Operate autonomously through planning, parallel subagent delegation, implementation, tests, review, and repair. This mode is only available when explicitly enabled by the gateway administrator and should run inside an isolated project container or VM.
""",
}

ROLE_INSTRUCTIONS = {
    "orchestrator": "Own decomposition, delegation, evidence gathering, implementation decisions, and final synthesis.",
    "planner": "Create a dependency-aware plan, milestones, risks, and acceptance tests. Do not edit files.",
    "architect": "Focus on architecture, interfaces, scalability, failure modes, and migration strategy.",
    "coder": "Inspect relevant code and propose implementation-ready changes or a unified diff. In review mode, do not apply it.",
    "reviewer": "Act as an adversarial reviewer. Find correctness, security, concurrency, compatibility, and test gaps.",
    "researcher": "Investigate repository evidence and technical options, distinguishing verified facts from assumptions.",
    "test": "Design and assess focused tests, reproduction steps, edge cases, and regression protection.",
    "security": "Threat-model the change and identify credential, sandbox, supply-chain, injection, and privilege risks.",
    "fast": "Return a concise, practical solution with minimal exploration.",
    "long_context": "Use the large context to connect cross-module behavior and hidden dependencies.",
    "hard_reasoning": "Work slowly on the most difficult logic, compare alternatives, and expose uncertainty.",
}


def build_task_prompt(
    prompt: str,
    mode: OrchestrationMode,
    system: str | None = None,
    *,
    role: str = "orchestrator",
) -> str:
    parts = [
        "[GATEWAY ORCHESTRATION POLICY]",
        MODE_INSTRUCTIONS[mode].strip(),
        f"[ASSIGNED ROLE]\n{ROLE_INSTRUCTIONS.get(role, role)}",
        "All available subagents may be used, but never expose credentials, OAuth tokens, environment secrets, or private session files.",
        "Do not attempt to bypass provider quotas, CAPTCHA, access controls, or account restrictions.",
    ]
    if system and system.strip():
        parts.extend(["[CALLER SYSTEM INSTRUCTIONS]", system.strip()])
    parts.extend(["[TASK]", prompt.strip()])
    return "\n\n".join(parts)


def flatten_openai_messages(messages: list[dict[str, Any]]) -> tuple[str | None, str]:
    system_parts: list[str] = []
    dialogue: list[str] = []
    for message in messages[-80:]:
        role = str(message.get("role", "user")).lower()
        content = message.get("content", "")
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "input_text"}:
                    texts.append(str(item.get("text") or item.get("input_text") or ""))
            content = "\n".join(texts)
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "system":
            system_parts.append(content.strip())
        else:
            dialogue.append(f"[{role.upper()}]\n{content.strip()}")
    if not dialogue:
        raise ValueError("At least one non-empty user message is required")
    system = "\n\n".join(system_parts) or None
    return system, "\n\n".join(dialogue)
