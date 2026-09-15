from codex_auto_router.config import AppConfig
from codex_auto_router.git_context import GitContext
from codex_auto_router.router import combine_scores, decide, heuristic_score, tier_for_score


def test_trivial_task_routes_to_luna_low():
    config = AppConfig()
    decision = decide("rename this variable", config, GitContext())
    assert decision.tier == "luna_low"
    assert decision.effort == "low"


def test_refactor_routes_above_luna_low():
    config = AppConfig()
    prompt = "Refactor the multi-file rendering pipeline and investigate a lifecycle regression."
    decision = decide(prompt, config, GitContext())
    assert decision.tier in {"terra_low", "terra_medium", "sol_medium"}


def test_git_context_can_raise_score_but_is_capped():
    prompt = "fix the bug"
    git = GitContext(is_repo=True, changed_files=50, diff_lines=5000)
    score, reasons = heuristic_score(prompt, git)
    assert score >= 2
    assert any("working tree" in reason.message or "diff" in reason.message for reason in reasons)


def test_tier_cap_prevents_expensive_route():
    config = AppConfig()
    config = AppConfig(
        routing=config.routing.__class__(max_auto_tier="terra_low"),
        codex=config.codex,
        routes=config.routes,
    )
    assert tier_for_score(12, config) == "terra_low"


def test_hybrid_score_weights_classifier():
    assert combine_scores(2, 8, "hybrid") == 6
