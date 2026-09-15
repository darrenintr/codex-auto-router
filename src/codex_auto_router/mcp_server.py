from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from .config import load_config
from .jobs import cancel_job, get_job, launch_job, tail_log

Tier = Literal["luna_low", "luna_medium", "terra_low", "terra_medium", "sol_medium"]


def create_server():
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised only without bridge dependencies
        raise RuntimeError(
            "MCP support is not installed. Install codex-auto-router with its bridge dependencies."
        ) from exc

    server = MCPServer(
        "Codex Auto Router",
        instructions=(
            "Dispatch coding tasks to the local Codex CLI only after choosing the cheapest sufficient tier. "
            "Use launch_codex for execution, get_codex_job for status, and get_codex_log only when details are needed."
        ),
    )

    @server.tool()
    def launch_codex(task: str, tier: Tier, workspace: str | None = None) -> dict:
        """Start a local Codex job with a preselected quota-conscious tier.

        This tool accepts only a coding task, a fixed routing tier, and an optional workspace path.
        It never accepts arbitrary shell commands. The local configuration enforces a maximum remote tier
        and allowed workspace roots before anything is launched.
        """
        config = load_config()
        try:
            record = launch_job(task, tier, workspace, config)
        except (ValueError, OSError) as exc:
            return {"error": "dispatch_rejected", "message": str(exc)}
        return asdict(record)

    @server.tool()
    def get_codex_job(job_id: str) -> dict:
        """Return the current state of a previously dispatched Codex job."""
        try:
            return asdict(get_job(job_id))
        except KeyError:
            return {"error": "job_not_found", "job_id": job_id}

    @server.tool()
    def get_codex_log(job_id: str, lines: int = 80) -> dict:
        """Return the tail of a Codex job log. Use only when the user asks for progress or diagnostics."""
        try:
            return {"job_id": job_id, "log": tail_log(job_id, lines)}
        except KeyError:
            return {"error": "job_not_found", "job_id": job_id}

    @server.tool()
    def cancel_codex_job(job_id: str) -> dict:
        """Cancel a running Codex job."""
        try:
            return asdict(cancel_job(job_id))
        except KeyError:
            return {"error": "job_not_found", "job_id": job_id}
        except RuntimeError as exc:
            return {"error": "cancel_failed", "job_id": job_id, "message": str(exc)}

    return server


def main() -> None:
    server = create_server()
    server.run("stdio")


if __name__ == "__main__":
    main()
