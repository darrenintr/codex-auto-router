from __future__ import annotations

from codex_auto_router.codex_first import (
    build_handoff_message,
    build_interactive_command,
    is_passthrough_invocation,
)


def test_codex_subcommands_bypass_router():
    assert is_passthrough_invocation(["plugin", "list"])
    assert is_passthrough_invocation(["login"])
    assert is_passthrough_invocation(["--model", "gpt-5.6-luna"])
    assert is_passthrough_invocation(["--direct"])


def test_plain_prompt_uses_router():
    assert not is_passthrough_invocation([])
    assert not is_passthrough_invocation(["fix the animation"])
    assert not is_passthrough_invocation(["--", "fix the animation"])


def test_interactive_command_preserves_task_and_route():
    command = build_interactive_command(
        "/usr/bin/codex",
        "gpt-5.6-terra",
        "low",
        "fix the rendering regression",
    )
    assert command[0] == "/usr/bin/codex"
    assert 'model="gpt-5.6-terra"' in command
    assert 'model_reasoning_effort="low"' in command
    assert command[-1] == "fix the rendering regression"


def test_handoff_is_explicitly_routing_only():
    handoff = build_handoff_message("route_deadbeef")
    assert "@codex-auto-router" in handoff
    assert "[CODEX_AUTO_ROUTE]" in handoff
    assert "route_deadbeef" in handoff
    assert "get_pending_codex_route" in handoff
    assert "submit_codex_route" in handoff
    assert "do not inspect, modify, or execute" in handoff
