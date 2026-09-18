from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import webbrowser

from .config import DEFAULT_CONFIG_PATH, TIER_ORDER, load_config
from .external_provider import choose_external_model, load_external_config
from .git_context import GitContext, collect_git_context
from .local_classifier import LocalClassifierError, classify_with_local_codex
from .repo_map import build_repo_map_context
from .route_requests import cancel_route_request, create_route_request, wait_for_route_decision
from .router import decide


PASSTHROUGH_SUBCOMMANDS = {
    "agents", "exec", "e", "review", "login", "logout", "mcp", "plugin", "app-server",
    "remote-control", "app", "completion", "update", "doctor", "sandbox", "debug", "apply",
    "a", "resume", "queue", "archive", "delete", "migrate-rollouts", "unarchive", "fork",
    "cloud", "cloud-tasks", "exec-server", "features",
}


def is_passthrough_invocation(argv: list[str]) -> bool:
    if os.environ.get("CODEX_AUTO_ROUTER_BYPASS") == "1":
        return True
    if not argv:
        return False
    if argv[0] == "--direct" or argv[0] in PASSTHROUGH_SUBCOMMANDS:
        return True
    return argv[0].startswith("-") and argv[0] != "--"


def _real_codex(binary: str) -> str:
    resolved = shutil.which(binary)
    if resolved is None:
        raise FileNotFoundError(binary)
    return resolved


def _passthrough(binary: str, argv: list[str]) -> int:
    if argv and argv[0] == "--direct":
        argv = argv[1:]
    resolved = _real_codex(binary)
    os.execv(resolved, [resolved, *argv])
    return 0


def _read_task(argv: list[str]) -> str:
    if argv and argv[0] == "--":
        argv = argv[1:]
    if argv:
        return " ".join(argv).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    try:
        return input("› ").strip()
    except EOFError:
        return ""


def _copy_to_clipboard(text: str) -> bool:
    commands: list[list[str]] = []
    if shutil.which("wl-copy"):
        commands.append(["wl-copy"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-selection", "clipboard"])
    if shutil.which("xsel"):
        commands.append(["xsel", "--clipboard", "--input"])
    if shutil.which("pbcopy"):
        commands.append(["pbcopy"])
    for command in commands:
        try:
            completed = subprocess.run(command, input=text, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0:
            return True
    return False


def build_interactive_command(binary: str, model: str, effort: str, task: str, model_provider: str | None = None) -> list[str]:
    command = [binary]
    if model_provider:
        command.extend(["-c", f'model_provider="{model_provider}"'])
    command.extend(["-c", f'model="{model}"', "-c", f'model_reasoning_effort="{effort}"', task])
    return command


def _fallback_tier(task: str, config, git: GitContext) -> str:
    decision = decide(task, config, git, strategy="heuristic")
    tier = decision.tier
    cap = config.routing.max_auto_tier if config.routing.max_auto_tier in TIER_ORDER else "sol_medium"
    if TIER_ORDER.index(tier) > TIER_ORDER.index(cap):
        tier = cap
    return tier


def _low_confidence_guard(tier: str, confidence: float, config) -> str:
    if confidence >= config.classifier.min_confidence:
        return tier
    cap = config.routing.max_auto_tier if config.routing.max_auto_tier in TIER_ORDER else "sol_medium"
    current = TIER_ORDER.index(tier)
    maximum = TIER_ORDER.index(cap)
    return TIER_ORDER[min(current + 1, maximum)]


def build_handoff_message(request_id: str) -> str:
    return (
        "@codex-auto-router [CODEX_AUTO_ROUTE] "
        f"route pending request {request_id}. "
        "Routing only: use get_pending_codex_route and submit_codex_route; "
        "do not inspect, modify, or execute the coding task in this chat."
    )


def _route_with_chatgpt(task: str, workspace: Path, config, git: GitContext) -> str | None:
    request = create_route_request(task, workspace, git)
    handoff = build_handoff_message(request.request_id)
    copied = config.chatgpt.copy_handoff and _copy_to_clipboard(handoff)
    if config.chatgpt.open_browser:
        try:
            webbrowser.open(config.chatgpt.url, new=2)
        except Exception:
            pass
    print(
        f"[codex-auto-router] waiting for ChatGPT route {request.request_id}\n"
        f"[codex-auto-router] workspace: {workspace}\n"
        f"[codex-auto-router] in ChatGPT send: {handoff}",
        file=sys.stderr,
    )
    if copied:
        print("[codex-auto-router] handoff message copied to clipboard", file=sys.stderr)
    try:
        decided = wait_for_route_decision(request.request_id, timeout_seconds=config.chatgpt.timeout_seconds)
        tier = decided.tier
        if tier is None:
            raise RuntimeError("route decision did not include a tier")
        reason = f" — {decided.reason}" if decided.reason else ""
        print(f"[codex-auto-router] ChatGPT selected {tier}{reason}", file=sys.stderr)
        return tier
    except KeyboardInterrupt:
        cancel_route_request(request.request_id)
        print("\n[codex-auto-router] routing cancelled", file=sys.stderr)
        return None
    except TimeoutError:
        if config.chatgpt.fallback != "heuristic":
            cancel_route_request(request.request_id)
            print("[codex-auto-router] ChatGPT routing timed out", file=sys.stderr)
            return None
        tier = _fallback_tier(task, config, git)
        print(f"[codex-auto-router] ChatGPT routing timed out; local fallback selected {tier}", file=sys.stderr)
        return tier
    except RuntimeError as exc:
        print(f"[codex-auto-router] routing stopped: {exc}", file=sys.stderr)
        return None


def _route_with_local_codex(task: str, workspace: Path, config, git: GitContext) -> str | None:
    repo_map = build_repo_map_context(task, workspace, config)
    if repo_map.available:
        token_note = f" (~{repo_map.estimated_tokens} tokens)" if repo_map.estimated_tokens is not None else ""
        print(f"[codex-auto-router] Repo Map context ready{token_note}", file=sys.stderr)
    else:
        print(f"[codex-auto-router] Repo Map unavailable ({repo_map.error}); classifier will use bounded read-only inspection", file=sys.stderr)
    route = config.routes.get(config.classifier.tier)
    classifier_name = f"{route.model}/{route.effort}" if route is not None else config.classifier.tier
    print(f"[codex-auto-router] classifying locally with {classifier_name}", file=sys.stderr)
    try:
        result = classify_with_local_codex(task, workspace, config, git, repo_map)
    except LocalClassifierError as exc:
        if config.classifier.fallback != "heuristic":
            print(f"[codex-auto-router] local classifier failed: {exc}", file=sys.stderr)
            return None
        tier = _fallback_tier(task, config, git)
        print(f"[codex-auto-router] local classifier failed ({exc}); heuristic fallback selected {tier}", file=sys.stderr)
        return tier
    except KeyboardInterrupt:
        print("\n[codex-auto-router] routing cancelled", file=sys.stderr)
        return None
    tier = _low_confidence_guard(result.tier, result.confidence, config)
    guard_note = f"; low-confidence guard raised {result.tier} -> {tier}" if tier != result.tier else ""
    reason = f" — {result.reason}" if result.reason else ""
    usage = result.usage
    print(
        f"[codex-auto-router] local classifier selected {tier} (confidence {result.confidence:.2f}{guard_note}){reason}\n"
        f"[codex-auto-router] classifier usage: input={usage.input_tokens}, cached={usage.cached_input_tokens}, "
        f"output={usage.output_tokens}, reasoning={usage.reasoning_output_tokens}",
        file=sys.stderr,
    )
    return tier


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    config = load_config(DEFAULT_CONFIG_PATH)
    if is_passthrough_invocation(argv):
        try:
            return _passthrough(config.codex.binary, argv)
        except FileNotFoundError:
            print(f"[codex-auto-router] Codex executable not found: {config.codex.binary}", file=sys.stderr)
            return 127

    task = _read_task(argv)
    if not task:
        print("[codex-auto-router] a task prompt is required", file=sys.stderr)
        return 2
    if len(task) > config.bridge.max_task_chars:
        print(f"[codex-auto-router] task exceeds max_task_chars={config.bridge.max_task_chars}", file=sys.stderr)
        return 2

    workspace = Path.cwd().resolve()
    git = collect_git_context(workspace) if config.routing.include_git_context else GitContext()
    if not git.is_repo:
        print("[codex-auto-router] warning: current directory is not inside a Git repository; Repo Map/Git context are unavailable but the exact directory will still be preserved", file=sys.stderr)

    mode = config.classifier.mode.strip().lower()
    if mode == "local":
        tier = _route_with_local_codex(task, workspace, config, git)
    elif mode == "chatgpt":
        tier = _route_with_chatgpt(task, workspace, config, git)
    elif mode == "heuristic":
        tier = _fallback_tier(task, config, git)
        print(f"[codex-auto-router] heuristic selected {tier}", file=sys.stderr)
    else:
        print(f"[codex-auto-router] unknown classifier.mode={config.classifier.mode!r}; expected local, chatgpt, or heuristic", file=sys.stderr)
        return 2
    if tier is None:
        return 4

    route = config.routes[tier]
    selected_model = route.model
    selected_provider: str | None = None
    external_config = load_external_config()
    external = choose_external_model(tier, external_config)
    if external is not None:
        selected_model = external.model
        selected_provider = external.codex_provider
        print(f"[codex-auto-router] external candidate selected {selected_model} via {selected_provider} — {external.reason}", file=sys.stderr)
    elif external_config.enabled and external_config.tier_models and external_config.tier_models.get(tier) and not external_config.fallback_official:
        print(f"[codex-auto-router] no external candidate for {tier} has usable capacity and fallback_official=false", file=sys.stderr)
        return 5
    elif external_config.enabled and external_config.tier_models and external_config.tier_models.get(tier):
        print(f"[codex-auto-router] no usable external candidate for {tier}; falling back to official {route.model}", file=sys.stderr)

    try:
        binary = _real_codex(config.codex.binary)
    except FileNotFoundError:
        print(f"[codex-auto-router] Codex executable not found: {config.codex.binary}", file=sys.stderr)
        return 127

    command = build_interactive_command(binary, selected_model, route.effort, task, selected_provider)
    os.chdir(workspace)
    os.execv(binary, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
