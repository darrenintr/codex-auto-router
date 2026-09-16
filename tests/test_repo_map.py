from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

from codex_auto_router.config import AppConfig
from codex_auto_router.repo_map import build_repo_map_context


def test_repo_map_context_uses_budget_and_stdin(monkeypatch, tmp_path: Path):
    config = AppConfig(classifier=replace(AppConfig().classifier, repo_map_budget=1777))
    captured = {}

    monkeypatch.setattr("codex_auto_router.repo_map.shutil.which", lambda name: "/usr/bin/codex-repo-map")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        payload = {
            "schema_version": 1,
            "task": "duplicated task",
            "project": {"name": "demo", "type": "python"},
            "budget": {"estimated_tokens": 640},
            "source_fallback": ["src/demo.py"],
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("codex_auto_router.repo_map.subprocess.run", fake_run)
    result = build_repo_map_context("fix parser bug", tmp_path, config)

    assert result.available
    assert result.estimated_tokens == 640
    assert result.payload is not None
    assert "task" not in result.payload
    assert captured["input"] == "fix parser bug"
    assert captured["cwd"] == tmp_path
    assert "1777" in captured["command"]


def test_repo_map_missing_binary_is_nonfatal(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("codex_auto_router.repo_map.shutil.which", lambda name: None)
    result = build_repo_map_context("task", tmp_path, AppConfig())
    assert not result.available
    assert "executable not found" in result.error
