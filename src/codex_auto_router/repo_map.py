from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .config import AppConfig


@dataclass(frozen=True)
class RepoMapResult:
    payload: dict[str, Any] | None
    error: str = ""

    @property
    def available(self) -> bool:
        return self.payload is not None

    @property
    def estimated_tokens(self) -> int | None:
        if not self.payload:
            return None
        budget = self.payload.get("budget")
        if not isinstance(budget, dict):
            return None
        value = budget.get("estimated_tokens")
        return int(value) if isinstance(value, (int, float)) else None


def build_repo_map_context(task: str, workspace: Path, config: AppConfig) -> RepoMapResult:
    """Return a compact Repo Map context, refreshing the local index first.

    Repo Map is an optimization, not a hard dependency. Any lookup failure is
    returned to the caller so local Codex classification can fall back to a
    bounded read-only repository inspection.
    """
    classifier = config.classifier
    if not classifier.repo_map_enabled:
        return RepoMapResult(None, "disabled")

    binary = shutil.which(classifier.repo_map_binary)
    if binary is None:
        return RepoMapResult(None, f"executable not found: {classifier.repo_map_binary}")

    command = [
        binary,
        "context",
        ".",
        "--budget",
        str(max(256, classifier.repo_map_budget)),
        "--json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            input=task,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, classifier.repo_map_timeout_seconds),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RepoMapResult(None, str(exc))

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        return RepoMapResult(None, detail[:1000])

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return RepoMapResult(None, f"invalid JSON: {exc}")
    if not isinstance(payload, dict):
        return RepoMapResult(None, "Repo Map returned a non-object payload")
    if payload.get("schema_version") != 1:
        return RepoMapResult(None, f"unsupported schema_version={payload.get('schema_version')!r}")

    # The classifier already receives the task separately. Avoid paying for it
    # twice in the prompt.
    payload = dict(payload)
    payload.pop("task", None)
    return RepoMapResult(payload)
