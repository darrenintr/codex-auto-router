from __future__ import annotations

from dataclasses import replace
import json

import pytest

from codex_auto_router.config import AppConfig
from codex_auto_router.git_context import GitContext
from codex_auto_router.local_classifier import (
    LocalClassifierError,
    build_classifier_prompt,
    parse_codex_jsonl,
)
from codex_auto_router.repo_map import RepoMapResult


def test_parse_codex_jsonl_reads_route_and_usage():
    output = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": '{"tier":"terra_low","confidence":0.91,"reason":"Cross-module debugging."}',
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 8123,
                        "cached_input_tokens": 4096,
                        "output_tokens": 42,
                        "reasoning_output_tokens": 17,
                    },
                }
            ),
        ]
    )

    result = parse_codex_jsonl(output, AppConfig())
    assert result.tier == "terra_low"
    assert result.confidence == pytest.approx(0.91)
    assert result.usage.input_tokens == 8123
    assert result.usage.cached_input_tokens == 4096
    assert result.usage.reasoning_output_tokens == 17


def test_classifier_rejects_tier_above_auto_cap():
    config = AppConfig(routing=replace(AppConfig().routing, max_auto_tier="terra_low"))
    output = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": '{"tier":"terra_medium","confidence":0.9,"reason":"broad"}',
            },
        }
    )
    with pytest.raises(LocalClassifierError, match="disallowed tier"):
        parse_codex_jsonl(output, config)


def test_prompt_prefers_repo_map_and_bounds_source_fallback():
    payload = {
        "schema_version": 1,
        "project": {"name": "demo", "type": "flutter"},
        "source_fallback": ["lib/a.dart", "lib/b.dart"],
        "budget": {"estimated_tokens": 900},
    }
    prompt = build_classifier_prompt(
        "fix reverse animation flicker",
        AppConfig(),
        GitContext(is_repo=True),
        RepoMapResult(payload),
    )
    assert "Use the Repo Map as the primary project context" in prompt
    assert "at most 3 files" in prompt
    assert "lib/a.dart" in prompt
    assert "do not run builds/tests" in prompt
