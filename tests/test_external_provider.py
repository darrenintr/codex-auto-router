from pathlib import Path

from codex_auto_router.codex_first import build_interactive_command
from codex_auto_router.external_provider import (
    ExternalConfig,
    choose_external_model,
    load_external_config,
)


def test_external_config_loads_tier_models(tmp_path: Path):
    path = tmp_path / "external.toml"
    path.write_text(
        """[external]
enabled = true
api_base = "http://127.0.0.1:8765"
codex_provider = "external"
prefer_free = true
min_remaining_tokens = 1000
capacity_max_age_seconds = 120

[tiers.luna_low]
models = ["openrouter/free-model", "groq/fallback"]
""",
        encoding="utf-8",
    )
    config = load_external_config(path)
    assert config.enabled is True
    assert config.capacity_max_age_seconds == 120
    assert config.tier_models["luna_low"] == (
        "openrouter/free-model",
        "groq/fallback",
    )


def test_selector_prefers_free_available_candidate(monkeypatch):
    capacity = {
        "providers": [
            {
                "provider": "openrouter",
                "state": "available",
                "available": True,
                "token": {
                    "remaining": None,
                    "accuracy": "unknown",
                },
            },
            {
                "provider": "groq",
                "state": "available",
                "available": True,
                "token": {
                    "remaining": 50000,
                    "accuracy": "observed",
                },
            },
        ]
    }
    models = {
        "data": [
            {"id": "openrouter/free-model", "free": True},
            {"id": "groq/fallback", "free": False},
        ]
    }

    def fake_get(url: str, timeout: float):
        return (
            capacity
            if url.endswith("/router/capacity")
            else models
        )

    monkeypatch.setattr(
        "codex_auto_router.external_provider._get_json",
        fake_get,
    )
    config = ExternalConfig(
        enabled=True,
        prefer_free=True,
        min_remaining_tokens=1000,
        tier_models={
            "luna_low": (
                "groq/fallback",
                "openrouter/free-model",
            )
        },
    )
    selected = choose_external_model("luna_low", config)
    assert selected is not None
    assert selected.model == "openrouter/free-model"
    assert selected.codex_provider == "external"


def test_selector_skips_exhausted_or_low_capacity(monkeypatch):
    capacity = {
        "providers": [
            {
                "provider": "openrouter",
                "state": "exhausted",
                "available": False,
                "token": {},
            },
            {
                "provider": "groq",
                "state": "available",
                "available": True,
                "token": {
                    "remaining": 500,
                    "accuracy": "observed",
                },
            },
        ]
    }
    models = {
        "data": [
            {"id": "openrouter/free-model", "free": True},
            {"id": "groq/fallback", "free": False},
        ]
    }
    monkeypatch.setattr(
        "codex_auto_router.external_provider._get_json",
        lambda url, timeout: (
            capacity
            if url.endswith("/router/capacity")
            else models
        ),
    )
    config = ExternalConfig(
        enabled=True,
        min_remaining_tokens=1000,
        tier_models={
            "luna_low": (
                "openrouter/free-model",
                "groq/fallback",
            )
        },
    )
    assert choose_external_model("luna_low", config) is None


def test_selector_does_not_permanently_trust_stale_rate_limit(monkeypatch):
    capacity = {
        "providers": [
            {
                "provider": "groq",
                "state": "limited",
                "available": False,
                "source": "observed_response_headers",
                "observed_at": "2000-01-01T00:00:00+00:00",
                "token": {
                    "remaining": 0,
                    "accuracy": "observed",
                },
            }
        ]
    }
    models = {
        "data": [
            {"id": "groq/model", "free": True},
        ]
    }
    monkeypatch.setattr(
        "codex_auto_router.external_provider._get_json",
        lambda url, timeout: (
            capacity
            if url.endswith("/router/capacity")
            else models
        ),
    )
    config = ExternalConfig(
        enabled=True,
        min_remaining_tokens=1000,
        capacity_max_age_seconds=60,
        tier_models={"luna_low": ("groq/model",)},
    )
    selected = choose_external_model("luna_low", config)
    assert selected is not None
    assert selected.model == "groq/model"
    assert "stale" in selected.reason


def test_selector_uses_conservative_credit_to_token_estimate(monkeypatch):
    capacity = {
        "providers": [
            {
                "provider": "openrouter",
                "state": "available",
                "available": True,
                "token": {
                    "remaining": None,
                    "accuracy": "unknown",
                },
                "credits": [
                    {
                        "currency": "USD",
                        "remaining": 1.0,
                        "accuracy": "exact",
                    }
                ],
            }
        ]
    }
    models = {
        "data": [
            {
                "id": "openrouter/paid-model",
                "free": False,
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
            }
        ]
    }
    monkeypatch.setattr(
        "codex_auto_router.external_provider._get_json",
        lambda url, timeout: (
            capacity
            if url.endswith("/router/capacity")
            else models
        ),
    )

    enough = ExternalConfig(
        enabled=True,
        min_remaining_tokens=400_000,
        tier_models={
            "luna_medium": ("openrouter/paid-model",)
        },
    )
    selected = choose_external_model("luna_medium", enough)
    assert selected is not None
    assert "500000" in selected.reason

    too_high = ExternalConfig(
        enabled=True,
        min_remaining_tokens=600_000,
        tier_models={
            "luna_medium": ("openrouter/paid-model",)
        },
    )
    assert choose_external_model("luna_medium", too_high) is None


def test_interactive_command_can_set_model_provider():
    command = build_interactive_command(
        "/usr/bin/codex",
        "openrouter/free-model",
        "low",
        "fix it",
        "external",
    )
    assert 'model_provider="external"' in command
    assert 'model="openrouter/free-model"' in command
    assert command[-1] == "fix it"
