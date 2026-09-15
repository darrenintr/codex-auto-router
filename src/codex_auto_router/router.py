from __future__ import annotations

from dataclasses import dataclass
import re

from .config import AppConfig, TIER_ORDER
from .git_context import GitContext


@dataclass(frozen=True)
class ScoreReason:
    points: int
    message: str


@dataclass(frozen=True)
class RouteDecision:
    score: int
    tier: str
    model: str
    effort: str
    reasons: tuple[ScoreReason, ...]
    heuristic_score: int
    classifier_score: int | None = None


WEIGHTED_PATTERNS: tuple[tuple[int, str, str], ...] = (
    (3, r"\b(architecture redesign|distributed system|race condition|deadlock|memory leak)\b", "deep systems work"),
    (2, r"\b(root cause|regression|cross-platform|concurrency|lifecycle|rendering pipeline)\b", "complex debugging signal"),
    (2, r"\b(refactor|migration|rewrite|multi-file|framework|performance|security)\b", "broad implementation signal"),
    (1, r"\b(debug|crash|failing test|build failure|investigate|optimi[sz]e)\b", "debugging signal"),
    (-1, r"\b(rename|typo|formatting|comment only|small change|one-line|simple change)\b", "small-change signal"),
)


def heuristic_score(prompt: str, git: GitContext | None = None) -> tuple[int, tuple[ScoreReason, ...]]:
    text = prompt.lower()
    reasons: list[ScoreReason] = []
    score = 0

    length = len(prompt)
    if length > 300:
        score += 1
        reasons.append(ScoreReason(1, "prompt is longer than 300 characters"))
    if length > 1000:
        score += 1
        reasons.append(ScoreReason(1, "prompt is longer than 1,000 characters"))
    if length > 2500:
        score += 1
        reasons.append(ScoreReason(1, "prompt is longer than 2,500 characters"))

    for points, pattern, label in WEIGHTED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            score += points
            reasons.append(ScoreReason(points, label))

    if prompt.count("\n") >= 12:
        score += 1
        reasons.append(ScoreReason(1, "task has many separate lines/instructions"))

    if git and git.is_repo:
        git_points = 0
        if git.changed_files > 5:
            git_points += 1
            reasons.append(ScoreReason(1, f"working tree has {git.changed_files} changed files"))
        if git.changed_files > 20:
            git_points += 1
            reasons.append(ScoreReason(1, "working tree is very broad"))
        if git.diff_lines > 500:
            git_points += 1
            reasons.append(ScoreReason(1, f"current diff is about {git.diff_lines} changed lines"))
        if git.diff_lines > 2000:
            git_points += 1
            reasons.append(ScoreReason(1, "current diff is very large"))
        # Existing repo dirtiness should not overwhelm the task itself.
        score += min(git_points, 2)

    return max(-2, min(score, 12)), tuple(reasons)


def tier_for_score(score: int, config: AppConfig) -> str:
    routing = config.routing
    if score <= routing.luna_low_max:
        tier = "luna_low"
    elif score <= routing.luna_medium_max:
        tier = "luna_medium"
    elif score <= routing.terra_low_max:
        tier = "terra_low"
    elif score <= routing.terra_medium_max:
        tier = "terra_medium"
    else:
        tier = "sol_medium"

    cap = routing.max_auto_tier
    if cap not in TIER_ORDER:
        cap = "sol_medium"
    if TIER_ORDER.index(tier) > TIER_ORDER.index(cap):
        return cap
    return tier


def combine_scores(heuristic: int, classifier: int | None, strategy: str) -> int:
    if strategy == "heuristic" or classifier is None:
        return heuristic
    if strategy == "ollama":
        return classifier
    if strategy == "hybrid":
        # The local classifier gets more weight, while heuristics keep routing stable.
        return round((classifier * 0.65) + (heuristic * 0.35))
    raise ValueError(f"Unknown routing strategy: {strategy}")


def decide(
    prompt: str,
    config: AppConfig,
    git: GitContext | None = None,
    *,
    classifier_score: int | None = None,
    strategy: str | None = None,
    force_tier: str | None = None,
) -> RouteDecision:
    heuristic, reasons = heuristic_score(prompt, git)
    strategy = strategy or config.routing.strategy
    score = combine_scores(heuristic, classifier_score, strategy)

    if force_tier:
        if force_tier not in config.routes:
            raise ValueError(f"Unknown tier: {force_tier}")
        tier = force_tier
    else:
        tier = tier_for_score(score, config)

    route = config.routes[tier]
    return RouteDecision(
        score=score,
        tier=tier,
        model=route.model,
        effort=route.effort,
        reasons=reasons,
        heuristic_score=heuristic,
        classifier_score=classifier_score,
    )
