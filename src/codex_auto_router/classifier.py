from __future__ import annotations

import json
from urllib import error, request

from .git_context import GitContext


class ClassifierError(RuntimeError):
    pass


def classify_with_ollama(
    prompt: str,
    *,
    model: str,
    base_url: str,
    git: GitContext | None = None,
    timeout: float = 8.0,
) -> int:
    git_summary = "not in a git repository"
    if git and git.is_repo:
        git_summary = (
            f"git repo; changed_files={git.changed_files}; "
            f"diff_lines={git.diff_lines}; untracked_files={git.untracked_files}"
        )

    system_prompt = """You classify coding task complexity for a quota-conscious model router.
Return JSON only: {\"score\": N}. N is an integer from 0 to 10.
0-1: trivial localized edit or lookup.
2-3: normal single-feature implementation or straightforward bug fix.
4-6: multi-file refactor, nontrivial debugging, build/test investigation.
7-9: architecture, subtle lifecycle/concurrency/performance issues, broad migration.
10: unusually difficult repository-wide reasoning.
Do not reward verbose wording by itself. Judge the actual engineering complexity."""

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "prompt": f"{system_prompt}\n\nRepository context: {git_summary}\n\nTask:\n{prompt}",
        "options": {"temperature": 0},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            outer = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ClassifierError(f"Ollama classifier unavailable: {exc}") from exc

    try:
        inner = json.loads(outer["response"])
        score = int(inner["score"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ClassifierError("Ollama returned an invalid classifier response") from exc

    return max(0, min(score, 10))
