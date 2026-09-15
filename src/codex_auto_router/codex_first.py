from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import webbrowser

from .config import DEFAULT_CONFIG_PATH, TIER_ORDER, load_config
from .git_context import GitContext, collect_git_context
from .route_requests import cancel_route_request, create_route_request, wait_for_route_decision
from .router import decide


PASSTHROUGH_SUBCOMMANDS = {
    "agents",
    "exec",
    "e",
    "review",
    "login",
    "logout",
    "mcp",
    "plugin",
    "app-server",
    "remote-control",
    "app",
    "completion",
    "update",
    "doctor",
    "sandbox",
    "debug",
    "apply",
    "a",
    "resume",
    "queue",
    "archive",
    "delete",
    "migrate-rollouts",
    "unarchive",
    "fork",
    "cloud",
    "cloud-tasks",
    "exec-server",
    "features",
}


def is_passthrough_invocation(argv: list[str]) -> bool:
    if os.environ.get("CODEX_AUTO_ROUTER_BYPASS") == "1":
        return True
    if not argv:
        return False
    if argv[0] == "--direct":
        return True
    if argv[0] in PASSTHROUGH_SUBCOMMANDS:
        return True
    if argv[0].startswith("-") and argv[0] != "--":
        return True
    return False


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
            completed = subprocess.run(
                command,
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0:
            return True
    return False


def build_interactive_command(binary: str, model: str, effort: str, task: str) -> list[str]:
    return [
        binary,
        "-c",
        f'model="{model}"',
        "-c",
        f'model_reasoning_effort="{effort}"',
        task,
    ]


def _fallback_tier(task: str, config, git: GitContext) -> str:
    decision = decide(task, config, git, strategy="heuristic")
    tier = decision.tier
    cap = config.bridge.max_remote_tier if config.bridge.max_remote_tier in TIER_ORDER else "terra_medium"
    if TIER_ORDER.index(tier) > TIER_ORDER.index(cap):
        tier = cap
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
        print(
            f"[codex-auto-router] task exceeds max_task_chars={config.bridge.max_task_chars}",
            file=sys.stderr,
        )
        return 2

    workspace = Path.cwd().resolve()
    git = collect_git_context(workspace) if config.routing.include_git_context else GitContext()
    request = create_route_request(task, workspace, git)
    handoff = f"@codex-auto-router route pending Codex request {request.request_id}"

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
        decided = wait_for_route_decision(
            request.request_id,
            timeout_seconds=config.chatgpt.timeout_seconds,
        )
        tier = decided.tier
        if tier is None:
            raise RuntimeError("route decision did not include a tier")
        reason = f" — {decided.reason}" if decided.reason else ""
        print(f"[codex-auto-router] ChatGPT selected {tier}{reason}", file=sys.stderr)
    except KeyboardInterrupt:
        cancel_route_request(request.request_id)
        print("\n[codex-auto-router] routing cancelled", file=sys.stderr)
        return 130
    except TimeoutError:
        if config.chatgpt.fallback != "heuristic":
            cancel_route_request(request.request_id)
            print("[codex-auto-router] ChatGPT routing timed out", file=sys.stderr)
            return 4
        tier = _fallback_tier(task, config, git)
        print(
            f"[codex-auto-router] ChatGPT routing timed out; local fallback selected {tier}",
            file=sys.stderr,
        )
    except RuntimeError as exc:
        print(f"[codex-auto-router] routing stopped: {exc}", file=sys.stderr)
        return 4

    route = config.routes[tier]
    try:
        binary = _real_codex(config.codex.binary)
    except FileNotFoundError:
        print(f"[codex-auto-router] Codex executable not found: {config.codex.binary}", file=sys.stderr)
        return 127

    command = build_interactive_command(binary, route.model, route.effort, task)
    os.chdir(workspace)
    os.execv(binary, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
