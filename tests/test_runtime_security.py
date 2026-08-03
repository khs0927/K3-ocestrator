from pathlib import Path

from app.acp_runtime import KimiAcpRuntime
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
