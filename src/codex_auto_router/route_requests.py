from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any

from .config import AppConfig
from .git_context import GitContext
from .jobs import validate_remote_tier


DEFAULT_ROUTE_REQUESTS_DIR = Path.home() / ".local" / "state" / "codex-auto-router" / "routes"


@dataclass(frozen=True)
class RouteRequest:
    request_id: str
    status: str
    task: str
    workspace: str
    created_at: str
    repo_root: str | None = None
    repo_remote: str | None = None
    branch: str | None = None
    changed_files: int = 0
    untracked_files: int = 0
    diff_lines: int = 0
    tier: str | None = None
    reason: str = ""
    confidence: float | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _requests_dir() -> Path:
    raw = os.environ.get("CODEX_AUTO_ROUTER_ROUTES_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_ROUTE_REQUESTS_DIR


def _request_path(request_id: str) -> Path:
    return _requests_dir() / f"{request_id}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_request(path: Path) -> RouteRequest:
    return RouteRequest(**json.loads(path.read_text(encoding="utf-8")))


def create_route_request(task: str, workspace: Path, git: GitContext) -> RouteRequest:
    task = task.strip()
    if not task:
        raise ValueError("task must not be empty")

    request = RouteRequest(
        request_id=f"route_{secrets.token_hex(8)}",
        status="pending",
        task=task,
        workspace=str(workspace.expanduser().resolve()),
        created_at=_utc_now(),
        repo_root=git.repo_root,
        repo_remote=git.remote,
        branch=git.branch,
        changed_files=git.changed_files,
        untracked_files=git.untracked_files,
        diff_lines=git.diff_lines,
    )
    _write_json(_request_path(request.request_id), asdict(request))
    return request


def get_route_request(request_id: str) -> RouteRequest:
    path = _request_path(request_id)
    if not path.exists():
        raise KeyError(request_id)
    return _read_request(path)


def get_latest_pending_route() -> RouteRequest:
    directory = _requests_dir()
    if not directory.exists():
        raise KeyError("no_pending_route")

    pending: list[RouteRequest] = []
    for path in directory.glob("route_*.json"):
        try:
            request = _read_request(path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if request.status == "pending":
            pending.append(request)

    if not pending:
        raise KeyError("no_pending_route")
    pending.sort(key=lambda request: request.created_at, reverse=True)
    return pending[0]


def submit_route_decision(
    request_id: str,
    tier: str,
    config: AppConfig,
    *,
    reason: str = "",
    confidence: float | None = None,
) -> RouteRequest:
    validate_remote_tier(tier, config)
    request = get_route_request(request_id)
    if request.status != "pending":
        raise ValueError(f"route request is not pending: {request.status}")

    if confidence is not None:
        confidence = max(0.0, min(float(confidence), 1.0))

    updated = replace(
        request,
        status="decided",
        tier=tier,
        reason=reason.strip()[:500],
        confidence=confidence,
    )
    _write_json(_request_path(request_id), asdict(updated))
    return updated


def cancel_route_request(request_id: str) -> RouteRequest:
    request = get_route_request(request_id)
    if request.status != "pending":
        return request
    updated = replace(request, status="cancelled")
    _write_json(_request_path(request_id), asdict(updated))
    return updated


def wait_for_route_decision(
    request_id: str,
    *,
    timeout_seconds: float,
    poll_interval: float = 0.25,
) -> RouteRequest:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        request = get_route_request(request_id)
        if request.status == "decided":
            return request
        if request.status == "cancelled":
            raise RuntimeError("route request was cancelled")
        if time.monotonic() >= deadline:
            raise TimeoutError(request_id)
        time.sleep(max(0.05, poll_interval))
