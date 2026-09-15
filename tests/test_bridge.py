from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from codex_auto_router.config import AppConfig, BridgeConfig, CodexConfig
from codex_auto_router.jobs import get_job, launch_job, resolve_workspace, validate_remote_tier
from codex_auto_router.runner import build_codex_exec_command


def make_config(root: Path, *, max_remote_tier: str = "terra_medium") -> AppConfig:
    base = AppConfig()
    return replace(
        base,
        codex=CodexConfig(binary="codex-test"),
        bridge=BridgeConfig(
            default_workspace=str(root),
            allowed_roots=(),
            max_remote_tier=max_remote_tier,
            max_task_chars=500,
            sandbox="workspace-write",
        ),
    )


def test_workspace_is_confined_to_allowed_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    config = make_config(allowed)

    child = allowed / "repo"
    child.mkdir()
    assert resolve_workspace(str(child), config) == child.resolve()

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="outside configured allowed roots"):
        resolve_workspace(str(outside), config)


def test_remote_tier_cap_blocks_expensive_route(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    config = make_config(root, max_remote_tier="terra_low")

    validate_remote_tier("luna_medium", config)
    validate_remote_tier("terra_low", config)
    with pytest.raises(ValueError, match="exceeds bridge max_remote_tier"):
        validate_remote_tier("terra_medium", config)


def test_launch_job_persists_metadata_without_shell(monkeypatch, tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    state = tmp_path / "jobs"
    monkeypatch.setenv("CODEX_AUTO_ROUTER_JOBS_DIR", str(state))
    config = make_config(root)

    seen = {}

    def fake_popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr("codex_auto_router.jobs.subprocess.Popen", fake_popen)

    record = launch_job("fix the focused regression", "luna_medium", None, config)
    assert record.status == "running"
    assert record.pid == 4242
    assert record.workspace == str(root.resolve())
    assert seen["command"][:3] == [sys.executable, "-m", "codex_auto_router.runner"]
    assert seen["kwargs"]["start_new_session"] is True

    persisted = get_job(record.job_id)
    assert persisted.tier == "luna_medium"
    assert persisted.task_preview == "fix the focused regression"


def test_runner_builds_sandboxed_codex_exec_command(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    config = make_config(root)
    record = SimpleNamespace(tier="terra_low", workspace=str(root))

    command = build_codex_exec_command(record, config)
    assert command[:2] == ["codex-test", "exec"]
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert command[command.index("--cd") + 1] == str(root)
    assert 'model="gpt-5.6-terra"' in command
    assert 'model_reasoning_effort="low"' in command
