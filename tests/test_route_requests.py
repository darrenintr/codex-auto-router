from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from codex_auto_router.config import AppConfig, BridgeConfig
from codex_auto_router.git_context import GitContext
from codex_auto_router.route_requests import (
    create_route_request,
    get_latest_pending_route,
    get_route_request,
    submit_route_decision,
    wait_for_route_decision,
)


def make_config(root: Path, *, max_remote_tier: str = "terra_medium") -> AppConfig:
    base = AppConfig()
    return replace(
        base,
        bridge=BridgeConfig(
            default_workspace=str(root),
            allowed_roots=(),
            max_remote_tier=max_remote_tier,
            max_task_chars=500,
            sandbox="workspace-write",
        ),
    )


def test_route_request_preserves_project_context(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CODEX_AUTO_ROUTER_ROUTES_DIR", str(tmp_path / "routes"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    git = GitContext(
        is_repo=True,
        changed_files=3,
        untracked_files=1,
        diff_lines=47,
        repo_root=str(workspace),
        branch="feature/router",
        remote="https://github.com/example/repo.git",
    )

    request = create_route_request("fix the route transition", workspace, git)
    assert request.status == "pending"
    assert request.workspace == str(workspace.resolve())
    assert request.branch == "feature/router"
    assert request.repo_remote == "https://github.com/example/repo.git"
    assert request.changed_files == 3

    latest = get_latest_pending_route()
    assert latest.request_id == request.request_id
    assert get_route_request(request.request_id).task == "fix the route transition"


def test_submitted_route_wakes_waiter(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CODEX_AUTO_ROUTER_ROUTES_DIR", str(tmp_path / "routes"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    config = make_config(workspace)

    request = create_route_request("implement a focused fix", workspace, GitContext())
    decided = submit_route_decision(
        request.request_id,
        "luna_medium",
        config,
        reason="Focused bug fix",
        confidence=0.91,
    )
    assert decided.status == "decided"
    assert decided.tier == "luna_medium"
    assert decided.confidence == 0.91

    waited = wait_for_route_decision(request.request_id, timeout_seconds=0.1)
    assert waited.tier == "luna_medium"


def test_route_decision_respects_local_tier_cap(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CODEX_AUTO_ROUTER_ROUTES_DIR", str(tmp_path / "routes"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    config = make_config(workspace, max_remote_tier="terra_low")
    request = create_route_request("debug a difficult issue", workspace, GitContext())

    with pytest.raises(ValueError, match="exceeds bridge max_remote_tier"):
        submit_route_decision(request.request_id, "terra_medium", config)
