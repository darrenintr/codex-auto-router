from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import os
import tomllib
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_EXTERNAL_CONFIG_PATH = Path.home() / ".config" / "codex-auto-router" / "external.toml"


@dataclass(frozen=True)
class ExternalConfig:
    enabled: bool = False
    api_base: str = "http://127.0.0.1:8765"
    codex_provider: str = "external"
    prefer_free: bool = True
    min_remaining_tokens: int = 0
    timeout_seconds: float = 1.5
    fallback_official: bool = True
    tier_models: dict[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class ExternalSelection:
    model: str
    codex_provider: str
    reason: str


def load_external_config(path: Path | None = None) -> ExternalConfig:
    raw_path = os.environ.get("CODEX_AUTO_ROUTER_EXTERNAL_CONFIG")
    path = path or (Path(raw_path).expanduser() if raw_path else DEFAULT_EXTERNAL_CONFIG_PATH)
    if not path.exists():
        return ExternalConfig()
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    ext = raw.get("external", {})
    tiers_raw = raw.get("tiers", {})
    tier_models: dict[str, tuple[str, ...]] = {}
    if isinstance(tiers_raw, dict):
        for tier, value in tiers_raw.items():
            if isinstance(value, dict):
                models = value.get("models", [])
            else:
                models = value
            if isinstance(models, str):
                models = [models]
            if isinstance(models, list):
                tier_models[str(tier)] = tuple(str(model) for model in models)
    return ExternalConfig(
        enabled=bool(ext.get("enabled", False)),
        api_base=str(ext.get("api_base", "http://127.0.0.1:8765")).rstrip("/"),
        codex_provider=str(ext.get("codex_provider", "external")),
        prefer_free=bool(ext.get("prefer_free", True)),
        min_remaining_tokens=max(0, int(ext.get("min_remaining_tokens", 0))),
        timeout_seconds=max(0.1, float(ext.get("timeout_seconds", 1.5))),
        fallback_official=bool(ext.get("fallback_official", True)),
        tier_models=tier_models,
    )


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "codex-auto-router"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - localhost/user-configured endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("external provider returned non-object JSON")
    return payload


def _provider_from_model(model: str) -> str | None:
    head, sep, _ = model.partition("/")
    return head if sep else None


def _capacity_by_provider(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("providers", []) if isinstance(payload.get("providers"), list) else []:
        if isinstance(item, dict) and item.get("provider"):
            result[str(item["provider"])] = item
    return result


def _models_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_models = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("models")
    result: dict[str, dict[str, Any]] = {}
    for item in raw_models or []:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"])] = item
    return result


def _capacity_allows(capacity: dict[str, Any] | None, minimum_tokens: int) -> tuple[bool, str]:
    if capacity is None:
        return True, "provider capacity not reported"
    if capacity.get("available") is False or capacity.get("state") in {"exhausted", "error"}:
        return False, f"provider state={capacity.get('state', 'unavailable')}"
    token = capacity.get("token") if isinstance(capacity.get("token"), dict) else {}
    remaining = token.get("remaining")
    accuracy = token.get("accuracy")
    if minimum_tokens > 0 and isinstance(remaining, int) and accuracy in {"exact", "observed"} and remaining < minimum_tokens:
        return False, f"remaining token window {remaining} < {minimum_tokens}"
    return True, f"provider state={capacity.get('state', 'unknown')}"


def choose_external_model(tier: str, config: ExternalConfig | None = None) -> ExternalSelection | None:
    config = config or load_external_config()
    if not config.enabled or not config.tier_models:
        return None
    candidates = list(config.tier_models.get(tier, ()))
    if not candidates:
        return None
    try:
        capacity = _capacity_by_provider(_get_json(f"{config.api_base}/router/capacity", config.timeout_seconds))
        models = _models_by_id(_get_json(f"{config.api_base}/router/models", config.timeout_seconds))
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    ranked: list[tuple[int, int, str, str]] = []
    for index, model in enumerate(candidates):
        provider = _provider_from_model(model)
        if provider is None:
            continue
        allowed, capacity_reason = _capacity_allows(capacity.get(provider), config.min_remaining_tokens)
        if not allowed:
            continue
        metadata = models.get(model, {})
        is_free = metadata.get("free") is True
        free_rank = 0 if config.prefer_free and is_free else 1
        ranked.append((free_rank, index, model, capacity_reason))
    if not ranked:
        return None
    _, _, model, capacity_reason = min(ranked)
    metadata = models.get(model, {})
    cost_note = "free" if metadata.get("free") is True else "configured candidate"
    return ExternalSelection(model=model, codex_provider=config.codex_provider, reason=f"{cost_note}; {capacity_reason}")
