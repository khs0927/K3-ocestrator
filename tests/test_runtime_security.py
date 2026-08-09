from types import SimpleNamespace

import pytest

from pathlib import Path

from app.acp_runtime import KimiAcpRuntime, KimiRuntimeError
from app.audit import AuditLogger
from app.config import Settings
from app.models import OrchestrationMode
from app.providers import ProviderRegistry


def runtime(tmp_path: Path) -> KimiAcpRuntime:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = Settings(_env_file=None, default_workspace=workspace, gateway_api_key="x", audit_log=tmp_path / "audit.jsonl")
    profile = ProviderRegistry.load().get("k3-256k")
    return KimiAcpRuntime(settings, AuditLogger(settings.audit_log), workspace=workspace, mode=OrchestrationMode.execute, profile=profile, thinking="high")


def test_path_scoped_grant_is_single_use(tmp_path: Path):
    rt = runtime(tmp_path)
    target = rt.workspace / "a.py"
    rt.grant_file_write({"path": str(target)})
    assert rt.consume_file_write_grant(target.resolve())
    assert not rt.consume_file_write_grant(target.resolve())


def test_missing_path_grants_only_one_write(tmp_path: Path):
    rt = runtime(tmp_path)
    rt.grant_file_write({"patch": "diff"})
    assert rt.consume_file_write_grant((rt.workspace / "a.py").resolve())
    assert not rt.consume_file_write_grant((rt.workspace / "b.py").resolve())


@pytest.mark.asyncio
async def test_reasoning_option_requires_supported_and_applied_value(tmp_path: Path):
    rt = runtime(tmp_path)
    rt.session_id = "session"
    options = [
        SimpleNamespace(
            id="thought-level",
            category="thought_level",
            current_value="high",
            options=[
                SimpleNamespace(value="low"),
                SimpleNamespace(value="high"),
                SimpleNamespace(value="max"),
            ],
        )
    ]
    calls = []

    class Connection:
        async def set_config_option(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                config_options=[
                    SimpleNamespace(
                        id="thought-level",
                        current_value=kwargs["value"],
                        options=options[0].options,
                    )
                ]
            )

    rt.conn = Connection()
    await rt._set_option(
        SimpleNamespace(config_options=options),
        category="thought_level",
        fallback_ids=("thinking", "reasoning_effort", "thought_level"),
        value="max",
    )
    assert calls[0]["value"] == "max"

    unsupported = SimpleNamespace(
        id="thought-level",
        category="thought_level",
        current_value="on",
        options=[SimpleNamespace(value="on")],
    )
    with pytest.raises(KimiRuntimeError, match="does not support reasoning effort"):
        await rt._set_option(
            SimpleNamespace(config_options=[unsupported]),
            category="thought_level",
            fallback_ids=("thinking", "reasoning_effort", "thought_level"),
            value="max",
        )


@pytest.mark.asyncio
async def test_reasoning_option_failure_is_not_silently_accepted(tmp_path: Path):
    rt = runtime(tmp_path)
    rt.session_id = "session"

    class Connection:
        async def set_config_option(self, **_kwargs):
            raise RuntimeError("simulated config failure")

    rt.conn = Connection()
    option = SimpleNamespace(
        id="thought-level",
        category="thought_level",
        current_value="high",
        options=[SimpleNamespace(value="low"), SimpleNamespace(value="high"), SimpleNamespace(value="max")],
    )
    with pytest.raises(KimiRuntimeError, match="Unable to apply reasoning effort"):
        await rt._set_option(
            SimpleNamespace(config_options=[option]),
            category="thought_level",
            fallback_ids=("thinking", "reasoning_effort", "thought_level"),
            value="max",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [None, SimpleNamespace(config_options=[]), SimpleNamespace(config_options=[SimpleNamespace(id="thought-level")])],
)
async def test_reasoning_option_requires_acp_confirmation(tmp_path: Path, response):
    rt = runtime(tmp_path)
    rt.session_id = "session"

    class Connection:
        async def set_config_option(self, **_kwargs):
            return response

    rt.conn = Connection()
    option = SimpleNamespace(
        id="thought-level",
        category="thought_level",
        current_value="high",
        options=[SimpleNamespace(value="low"), SimpleNamespace(value="high"), SimpleNamespace(value="max")],
    )
    with pytest.raises(KimiRuntimeError, match="ACP (returned no confirmation|response omitted)"):
        await rt._set_option(
            SimpleNamespace(config_options=[option]),
            category="thought_level",
            fallback_ids=("thinking", "reasoning_effort", "thought_level"),
            value="max",
        )


@pytest.mark.asyncio
async def test_reasoning_option_requires_acp_advertisement(tmp_path: Path):
    rt = runtime(tmp_path)
    with pytest.raises(KimiRuntimeError, match="did not advertise"):
        await rt._set_option(
            SimpleNamespace(config_options=[]),
            category="thought_level",
            fallback_ids=("thinking", "reasoning_effort", "thought_level"),
            value="max",
        )
