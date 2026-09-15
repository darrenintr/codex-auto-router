from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from .config import DEFAULT_STATE_PATH
from .git_context import GitContext
from .router import RouteDecision


def record_decision(
    prompt: str,
    decision: RouteDecision,
    strategy: str,
    git: GitContext | None,
    path: Path | None = None,
) -> None:
    path = path or DEFAULT_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_sha256": sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(prompt),
        "strategy": strategy,
        "score": decision.score,
        "heuristic_score": decision.heuristic_score,
        "classifier_score": decision.classifier_score,
        "tier": decision.tier,
        "model": decision.model,
        "effort": decision.effort,
        "repo_root": git.repo_root if git else None,
        "changed_files": git.changed_files if git else 0,
        "diff_lines": git.diff_lines if git else 0,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
