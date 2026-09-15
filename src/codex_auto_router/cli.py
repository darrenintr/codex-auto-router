from __future__ import annotations

import argparse
from pathlib import Path
import os
import shlex
import shutil
import sys

from . import __version__
from .classifier import ClassifierError, classify_with_ollama
from .config import DEFAULT_CONFIG_PATH, TIER_ORDER, load_config, write_default_config
from .git_context import GitContext, collect_git_context
from .history import record_decision
from .router import decide


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-auto",
        description="Route Codex CLI tasks to a quota-conscious model/reasoning tier.",
    )
    parser.add_argument("prompt", nargs="*", help="Task to send to Codex")
    parser.add_argument("--stdin", action="store_true", help="Read the complete task from standard input")
    parser.add_argument("--dry-run", action="store_true", help="Choose a route without launching Codex")
    parser.add_argument("--explain", action="store_true", help="Show why the route was selected")
    parser.add_argument("--print-command", action="store_true", help="Print the Codex command before execution")
    parser.add_argument("--strategy", choices=("heuristic", "ollama", "hybrid"), help="Override routing strategy")
    parser.add_argument("--classifier-model", help="Override the Ollama classifier model")
    parser.add_argument("--force-tier", choices=TIER_ORDER, help="Bypass auto-routing and use a specific tier")
    parser.add_argument("--no-git-context", action="store_true", help="Do not inspect the current Git repository")
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    parser.add_argument("--init-config", action="store_true", help="Create the default config and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _split_passthrough(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def _format_decision(decision, strategy: str) -> str:
    classifier = ""
    if decision.classifier_score is not None:
        classifier = f", classifier={decision.classifier_score}"
    return (
        f"[codex-auto] {decision.tier}: {decision.model} / {decision.effort} "
        f"(score={decision.score}, heuristic={decision.heuristic_score}{classifier}, strategy={strategy})"
    )


def _build_command(binary: str, model: str, effort: str, prompt: str, passthrough: list[str]) -> list[str]:
    return [
        binary,
        "-c",
        f'model="{model}"',
        "-c",
        f'model_reasoning_effort="{effort}"',
        *passthrough,
        prompt,
    ]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    router_argv, passthrough = _split_passthrough(argv)
    parser = build_parser()
    args = parser.parse_args(router_argv)

    config_path = args.config or DEFAULT_CONFIG_PATH
    if args.init_config:
        try:
            path = write_default_config(config_path)
        except FileExistsError:
            print(f"Config already exists: {config_path}", file=sys.stderr)
            return 2
        print(f"Created {path}")
        return 0

    config = load_config(config_path)
    if args.stdin and args.prompt:
        parser.error("--stdin cannot be combined with a positional task prompt")

    if args.stdin:
        prompt = sys.stdin.read().strip()
    else:
        prompt = " ".join(args.prompt).strip()
        if not prompt:
            try:
                prompt = input("Task: ").strip()
            except EOFError:
                prompt = ""
    if not prompt:
        parser.error("a task prompt is required")

    use_git = config.routing.include_git_context and not args.no_git_context
    git = collect_git_context() if use_git else GitContext()
    strategy = args.strategy or config.routing.strategy
    classifier_score = None

    if strategy in {"ollama", "hybrid"}:
        try:
            classifier_score = classify_with_ollama(
                prompt,
                model=args.classifier_model or config.routing.ollama_model,
                base_url=config.routing.ollama_url,
                git=git,
            )
        except ClassifierError as exc:
            if strategy == "ollama":
                print(f"[codex-auto] {exc}", file=sys.stderr)
                return 3
            print(f"[codex-auto] {exc}; falling back to heuristics", file=sys.stderr)
            strategy = "heuristic"

    decision = decide(
        prompt,
        config,
        git,
        classifier_score=classifier_score,
        strategy=strategy,
        force_tier=args.force_tier,
    )

    print(_format_decision(decision, strategy), file=sys.stderr)
    if args.explain:
        if not decision.reasons:
            print("  no complexity signals; using the cheapest tier", file=sys.stderr)
        for reason in decision.reasons:
            sign = "+" if reason.points >= 0 else ""
            print(f"  {sign}{reason.points}: {reason.message}", file=sys.stderr)

    if config.routing.save_history:
        try:
            record_decision(prompt, decision, strategy, git)
        except OSError as exc:
            print(f"[codex-auto] warning: could not write history: {exc}", file=sys.stderr)

    command = _build_command(config.codex.binary, decision.model, decision.effort, prompt, passthrough)
    if args.print_command or args.dry_run:
        print(shlex.join(command))
    if args.dry_run:
        return 0

    binary = shutil.which(config.codex.binary)
    if binary is None:
        print(
            f"[codex-auto] Codex executable not found: {config.codex.binary}. "
            "Install Codex CLI or set [codex].binary in config.toml.",
            file=sys.stderr,
        )
        return 127

    command[0] = binary
    os.execv(binary, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
