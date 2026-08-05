from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.expanduser().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8790
    gateway_api_key: str = ""
    mcp_internal_api_key: str = ""

    # API credentials are loaded from .env but are never written to logs.
    nvidia_api_key: str = ""
    deepseek_api_key: str = ""
    zai_api_key: str = ""
    ds2api_enabled: bool = False
    ds2api_base_url: str = "http://127.0.0.1:5001/v1"
    ds2api_api_key: str = ""
    ds2api_api_key_file: Path | None = None

    kimi_command: str = "kimi"
    kimi_code_home: Path = Path("./data/kimi-code-home")
    default_workspace: Path = Path("./workspace")
    default_model: str = "k3-256k"
    default_role: str = "orchestrator"
    default_thinking: str = "high"

    provider_profiles_file: Path = Path("./config/provider-profiles.json")
    routing_file: Path = Path("./config/routes.json")

    prompt_timeout_seconds: float = 7200.0
    approval_timeout_seconds: float = 600.0
    max_live_sessions: int = Field(default=8, ge=1, le=64)
    session_idle_ttl_seconds: float = 3600.0
    max_parallel_subagents: int = Field(default=6, ge=1, le=32)
    max_route_attempts: int = Field(default=3, ge=1, le=3)

    allow_execute_mode: bool = True
    allow_yolo_mode: bool = False
    allow_paths: list[Path] = Field(default_factory=list)
    read_only_command_prefixes: list[str] = Field(
        default_factory=lambda: [
            "git status",
            "git diff",
            "git log",
            "git show",
            "pytest --collect-only",
            "npm test -- --listTests",
            "pnpm test -- --list",
        ]
    )
    safe_test_command_prefixes: list[str] = Field(
        default_factory=lambda: [
            "pytest",
            "python -m pytest",
            "npm test",
            "pnpm test",
            "npm run test",
            "pnpm run test",
            "cargo test",
            "go test",
            "dotnet test",
        ]
    )

    enable_web_advisory_fallback: bool = False
    deepseek_web_bridge_url: str = ""
    deepseek_web_bridge_key: str = ""
    glm_web_bridge_url: str = ""
    glm_web_bridge_key: str = ""

    enable_self_mcp: bool = True
    self_mcp_python: str = ""

    audit_log: Path = Path("./data/audit.jsonl")
    state_file: Path = Path("./data/gateway-state.json")

    def resolved_ds2api_api_key(self) -> str:
        return self.ds2api_api_key.strip() or _read_secret_file(self.ds2api_api_key_file)

    def prepare(self) -> None:
        self.kimi_code_home.mkdir(parents=True, exist_ok=True)
        self.default_workspace.mkdir(parents=True, exist_ok=True)
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.provider_profiles_file.parent.mkdir(parents=True, exist_ok=True)
        self.routing_file.parent.mkdir(parents=True, exist_ok=True)

    def workspace_roots(self) -> list[Path]:
        roots = [self.default_workspace, *self.allow_paths]
        return [path.expanduser().resolve() for path in roots]


settings = Settings()
