from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import os
import tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "codex-auto-router" / "config.toml"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "codex-auto-router" / "history.jsonl"

TIER_ORDER = ("luna_low", "luna_medium", "terra_low", "terra_medium", "sol_medium")


@dataclass(frozen=True)
class ModelRoute:
    model: str
    effort: str


@dataclass(frozen=True)
class RoutingConfig:
    luna_low_max: int = 1
    luna_medium_max: int = 3
    terra_low_max: int = 6
    terra_medium_max: int = 9
    max_auto_tier: str = "sol_medium"
    include_git_context: bool = True
    strategy: str = "heuristic"
    ollama_model: str = "qwen3:1.7b"
    ollama_url: str = "http://127.0.0.1:11434"
    save_history: bool = True


@dataclass(frozen=True)
class CodexConfig:
    binary: str = "codex"


@dataclass(frozen=True)
class AppConfig:
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    routes: dict[str, ModelRoute] = field(
        default_factory=lambda: {
            "luna_low": ModelRoute("gpt-5.6-luna", "low"),
            "luna_medium": ModelRoute("gpt-5.6-luna", "medium"),
            "terra_low": ModelRoute("gpt-5.6-terra", "low"),
            "terra_medium": ModelRoute("gpt-5.6-terra", "medium"),
            "sol_medium": ModelRoute("gpt-5.6-sol", "medium"),
        }
    )


DEFAULT_CONFIG_TEXT = '''# codex-auto-router configuration
# Model availability can vary by account. Change these names to match your Codex model picker.

[routing]
strategy = "heuristic"        # heuristic | ollama | hybrid
include_git_context = true
save_history = true
max_auto_tier = "sol_medium"  # never routes above this tier

# Heuristic score thresholds.
luna_low_max = 1
luna_medium_max = 3
terra_low_max = 6
terra_medium_max = 9

# Optional local classifier. Only used when strategy is ollama or hybrid.
ollama_model = "qwen3:1.7b"
ollama_url = "http://127.0.0.1:11434"

[codex]
binary = "codex"

[routes.luna_low]
model = "gpt-5.6-luna"
effort = "low"

[routes.luna_medium]
model = "gpt-5.6-luna"
effort = "medium"

[routes.terra_low]
model = "gpt-5.6-terra"
effort = "low"

[routes.terra_medium]
model = "gpt-5.6-terra"
effort = "medium"

[routes.sol_medium]
model = "gpt-5.6-sol"
effort = "medium"
'''


def _route_from(raw: dict, fallback: ModelRoute) -> ModelRoute:
    return ModelRoute(
        model=str(raw.get("model", fallback.model)),
        effort=str(raw.get("effort", fallback.effort)),
    )


def load_config(path: Path | None = None) -> AppConfig:
    config = AppConfig()
    path = path or Path(os.environ.get("CODEX_AUTO_ROUTER_CONFIG", DEFAULT_CONFIG_PATH))
    if not path.exists():
        return config

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    routing_raw = raw.get("routing", {})
    routing = replace(
        config.routing,
        luna_low_max=int(routing_raw.get("luna_low_max", config.routing.luna_low_max)),
        luna_medium_max=int(routing_raw.get("luna_medium_max", config.routing.luna_medium_max)),
        terra_low_max=int(routing_raw.get("terra_low_max", config.routing.terra_low_max)),
        terra_medium_max=int(routing_raw.get("terra_medium_max", config.routing.terra_medium_max)),
        max_auto_tier=str(routing_raw.get("max_auto_tier", config.routing.max_auto_tier)),
        include_git_context=bool(routing_raw.get("include_git_context", config.routing.include_git_context)),
        strategy=str(routing_raw.get("strategy", config.routing.strategy)),
        ollama_model=str(routing_raw.get("ollama_model", config.routing.ollama_model)),
        ollama_url=str(routing_raw.get("ollama_url", config.routing.ollama_url)),
        save_history=bool(routing_raw.get("save_history", config.routing.save_history)),
    )

    codex_raw = raw.get("codex", {})
    codex = replace(config.codex, binary=str(codex_raw.get("binary", config.codex.binary)))

    routes_raw = raw.get("routes", {})
    routes = {
        name: _route_from(routes_raw.get(name, {}), route)
        for name, route in config.routes.items()
    }

    return AppConfig(routing=routing, codex=codex, routes=routes)


def write_default_config(path: Path | None = None, *, overwrite: bool = False) -> Path:
    path = path or DEFAULT_CONFIG_PATH
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
    return path
