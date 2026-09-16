from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .config import AppConfig, TIER_ORDER
from .git_context import GitContext
from .repo_map import RepoMapResult


class LocalClassifierError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClassifierUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0


@dataclass(frozen=True)
class LocalClassification:
    tier: str
    confidence: float
    reason: str
    usage: ClassifierUsage


def _allowed_tiers(config: AppConfig) -> tuple[str, ...]:
    cap = config.routing.max_auto_tier
    if cap not in TIER_ORDER:
        cap = "sol_medium"
    return TIER_ORDER[: TIER_ORDER.index(cap) + 1]


def build_classifier_prompt(
    task: str,
    config: AppConfig,
    git: GitContext,
    repo_map: RepoMapResult,
) -> str:
    allowed = _allowed_tiers(config)
    routing_ladder = "\n".join(
        [
            "- luna_low: deterministic local edits, renames, formatting, tiny UI tweaks.",
            "- luna_medium: normal features, focused bug fixes, routine tests and UI work.",
            "- terra_low: multi-file work, build failures, nontrivial debugging, moderate refactors.",
            "- terra_medium: subtle regressions, lifecycle/rendering/concurrency issues, broad refactors or migrations.",
            "- sol_medium: unusually difficult architecture/debugging only.",
        ]
    )
    repo_section: str
    if repo_map.payload is not None:
        repo_section = json.dumps(repo_map.payload, ensure_ascii=False, separators=(",", ":"))
        fallback_rule = (
            "Use the Repo Map as the primary project context. If that is not enough to reach the confidence "
            f"threshold, you may read at most {config.classifier.max_source_fallback_files} files and only from "
            "the Repo Map source_fallback list. Do not inspect unrelated files."
        )
    else:
        repo_section = json.dumps(
            {
                "available": False,
                "error": repo_map.error,
                "git": asdict(git),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        fallback_rule = (
            "Repo Map is unavailable. Perform only bounded read-only discovery: project/root metadata plus at most "
            f"{config.classifier.max_source_fallback_files} targeted source files. Do not explore the repository broadly."
        )

    return f"""You are the classification stage of Codex Auto Router.
Your only job is to choose the cheapest Codex tier likely to complete the user's coding task reliably.
Do not solve the task, do not produce an implementation plan, do not modify files, do not run builds/tests, and do not make network requests.
The sandbox is read-only.

Allowed tiers: {', '.join(allowed)}
Routing ladder:
{routing_ladder}

Classification signals:
- likely file/subsystem scope;
- whether the root cause is unknown;
- cross-platform behavior;
- lifecycle, rendering, concurrency, race-condition, memory, security, or performance complexity;
- architecture changes, migrations, or repository-wide refactors;
- whether the requested change is small and deterministic;
- current working-tree size only as supporting evidence, not the main reason to escalate.

Default to Luna. Use Terra only for concrete complexity. Use Sol only for unusually difficult architecture/debugging.
{fallback_rule}
If you inspect source, stop as soon as you have enough evidence to classify.

Minimum desired confidence: {config.classifier.min_confidence:.2f}

USER TASK:
{task}

COMPACT PROJECT CONTEXT:
{repo_section}

Return exactly one JSON object and no markdown:
{{"tier":"luna_low|luna_medium|terra_low|terra_medium|sol_medium","confidence":0.0,"reason":"one short sentence"}}
The tier must be one of the Allowed tiers listed above.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise LocalClassifierError("classifier did not return JSON")
        try:
            value = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LocalClassifierError(f"invalid classifier JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LocalClassifierError("classifier returned a non-object JSON value")
    return value


def parse_codex_jsonl(output: str, config: AppConfig) -> LocalClassification:
    final_text = ""
    usage = ClassifierUsage()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                final_text = item["text"]
        elif event.get("type") == "turn.completed":
            raw_usage = event.get("usage")
            if isinstance(raw_usage, dict):
                usage = ClassifierUsage(
                    input_tokens=int(raw_usage.get("input_tokens") or 0),
                    cached_input_tokens=int(raw_usage.get("cached_input_tokens") or 0),
                    output_tokens=int(raw_usage.get("output_tokens") or 0),
                    reasoning_output_tokens=int(raw_usage.get("reasoning_output_tokens") or 0),
                )

    if not final_text:
        raise LocalClassifierError("Codex classifier produced no final agent message")
    payload = _extract_json_object(final_text)
    tier = str(payload.get("tier", ""))
    allowed = _allowed_tiers(config)
    if tier not in allowed:
        raise LocalClassifierError(f"classifier returned disallowed tier: {tier!r}")
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise LocalClassifierError("classifier returned invalid confidence") from exc
    confidence = max(0.0, min(confidence, 1.0))
    reason = str(payload.get("reason", "")).strip()[:500]
    return LocalClassification(tier=tier, confidence=confidence, reason=reason, usage=usage)


def classify_with_local_codex(
    task: str,
    workspace: Path,
    config: AppConfig,
    git: GitContext,
    repo_map: RepoMapResult,
) -> LocalClassification:
    classifier_tier = config.classifier.tier
    if classifier_tier not in config.routes:
        raise LocalClassifierError(f"unknown classifier tier: {classifier_tier}")
    route = config.routes[classifier_tier]

    binary = shutil.which(config.codex.binary)
    if binary is None:
        raise LocalClassifierError(f"Codex executable not found: {config.codex.binary}")

    prompt = build_classifier_prompt(task, config, git, repo_map)
    command = [
        binary,
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "-c",
        f'model="{route.model}"',
        "-c",
        f'model_reasoning_effort="{route.effort}"',
        prompt,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, config.classifier.timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalClassifierError("local Codex classifier timed out") from exc
    except OSError as exc:
        raise LocalClassifierError(str(exc)) from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise LocalClassifierError(f"local Codex classifier failed: {detail[:1200]}")
    return parse_codex_jsonl(completed.stdout, config)
