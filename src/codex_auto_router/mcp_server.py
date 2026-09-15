from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from .config import load_config
from .jobs import cancel_job, get_job, launch_job, tail_log
from .route_requests import get_latest_pending_route, get_route_request, submit_route_decision

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
            "Route coding tasks with the cheapest sufficient Codex tier. "
            "For Codex-first handoffs, read a pending request with get_pending_codex_route and return the decision "
            "with submit_codex_route; the waiting local launcher will start Codex itself. "
            "Use launch_codex only for ChatGPT-first tasks that do not already have a pending route request."
        ),
    )

    @server.tool()
    def get_pending_codex_route(request_id: str | None = None) -> dict:
        """Return a pending Codex-first routing request created by the local launcher.

        When request_id is omitted, the newest pending request is returned. The result includes the user's task,
        current workspace, Git root/remote/branch when available, and a small working-tree size summary.
        This tool does not start Codex or consume a Codex task turn.
        """
        try:
            request = get_route_request(request_id) if request_id else get_latest_pending_route()
        except KeyError:
            return {"error": "route_not_found", "request_id": request_id}
        return asdict(request)

    @server.tool()
    def submit_codex_route(
        request_id: str,
        tier: Tier,
        reason: str = "",
        confidence: float | None = None,
    ) -> dict:
        """Submit ChatGPT's route decision to a waiting local Codex-first launcher.

        The local bridge validates the tier cap before accepting the decision. Do not call launch_codex after a
        successful submit for the same request; the local launcher resumes and starts Codex automatically.
        """
        config = load_config()
        try:
            request = submit_route_decision(
                request_id,
                tier,
                config,
                reason=reason,
                confidence=confidence,
            )
        except KeyError:
            return {"error": "route_not_found", "request_id": request_id}
        except ValueError as exc:
            return {"error": "route_rejected", "request_id": request_id, "message": str(exc)}
        return asdict(request)

    @server.tool()
    def launch_codex(task: str, tier: Tier, workspace: str | None = None) -> dict:
        """Start a local Codex job with a preselected quota-conscious tier.

        Use this only for ChatGPT-first dispatches. If a pending Codex-first route request exists, submit its route
        decision instead so the already-waiting local launcher can preserve its project context and start Codex.
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
