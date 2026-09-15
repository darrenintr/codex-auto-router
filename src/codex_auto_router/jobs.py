from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
from typing import Any

from .config import AppConfig, TIER_ORDER


DEFAULT_JOBS_DIR = Path.home() / ".local" / "state" / "codex-auto-router" / "jobs"


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    task_preview: str
    tier: str
    model: str
    effort: str
    workspace: str
    status: str
    created_at: str
    pid: int | None = None
    exit_code: int | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jobs_dir() -> Path:
    raw = os.environ.get("CODEX_AUTO_ROUTER_JOBS_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_JOBS_DIR


def _job_dir(job_id: str) -> Path:
    return _jobs_dir() / job_id


def _metadata_path(job_id: str) -> Path:
    return _job_dir(job_id) / "job.json"


def _task_path(job_id: str) -> Path:
    return _job_dir(job_id) / "task.txt"


def _log_path(job_id: str) -> Path:
    return _job_dir(job_id) / "codex.log"


def _exit_path(job_id: str) -> Path:
    return _job_dir(job_id) / "exit.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_workspace(requested: str | None, config: AppConfig) -> Path:
    bridge = config.bridge
    if bridge.default_workspace:
        default = Path(bridge.default_workspace).expanduser().resolve()
    else:
        default = Path.cwd().resolve()

    workspace = Path(requested).expanduser().resolve() if requested else default
    roots = [default]
    roots.extend(Path(value).expanduser().resolve() for value in bridge.allowed_roots)

    if not any(workspace == root or _is_relative_to(workspace, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise ValueError(f"workspace is outside configured allowed roots: {allowed}")
    if not workspace.is_dir():
        raise ValueError(f"workspace does not exist or is not a directory: {workspace}")
    return workspace


def validate_remote_tier(tier: str, config: AppConfig) -> None:
    if tier not in TIER_ORDER:
        raise ValueError(f"unknown tier: {tier}")
    cap = config.bridge.max_remote_tier
    if cap not in TIER_ORDER:
        cap = "terra_medium"
    if TIER_ORDER.index(tier) > TIER_ORDER.index(cap):
        raise ValueError(f"tier {tier} exceeds bridge max_remote_tier={cap}")


def launch_job(task: str, tier: str, workspace: str | None, config: AppConfig) -> JobRecord:
    task = task.strip()
    if not task:
        raise ValueError("task must not be empty")
    if len(task) > config.bridge.max_task_chars:
        raise ValueError(f"task exceeds max_task_chars={config.bridge.max_task_chars}")

    validate_remote_tier(tier, config)
    workspace_path = resolve_workspace(workspace, config)
    route = config.routes[tier]
    job_id = f"job_{secrets.token_hex(8)}"
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=False)
    _task_path(job_id).write_text(task, encoding="utf-8")

    record = JobRecord(
        job_id=job_id,
        task_preview=task.replace("\n", " ")[:160],
        tier=tier,
        model=route.model,
        effort=route.effort,
        workspace=str(workspace_path),
        status="starting",
        created_at=_utc_now(),
    )
    _write_json(_metadata_path(job_id), asdict(record))

    command = [
        sys.executable,
        "-m",
        "codex_auto_router.runner",
        "--job-id",
        job_id,
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )

    record = JobRecord(**{**asdict(record), "status": "running", "pid": process.pid})
    _write_json(_metadata_path(job_id), asdict(record))
    return record


def get_job(job_id: str) -> JobRecord:
    metadata = _metadata_path(job_id)
    if not metadata.exists():
        raise KeyError(job_id)
    payload = _read_json(metadata)
    exit_path = _exit_path(job_id)
    if exit_path.exists():
        exit_payload = _read_json(exit_path)
        payload["status"] = "completed" if exit_payload.get("exit_code") == 0 else "failed"
        payload["exit_code"] = int(exit_payload.get("exit_code", 1))
    return JobRecord(**payload)


def tail_log(job_id: str, lines: int = 80) -> str:
    if not _metadata_path(job_id).exists():
        raise KeyError(job_id)
    path = _log_path(job_id)
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-max(1, min(lines, 400)):])


def cancel_job(job_id: str) -> JobRecord:
    record = get_job(job_id)
    if record.status in {"completed", "failed", "cancelled"}:
        return record
    if record.pid is None:
        raise RuntimeError("job has no process id")
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(record.pid), signal.SIGTERM)
        else:  # pragma: no cover - Windows fallback
            os.kill(record.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    payload = asdict(record)
    payload["status"] = "cancelled"
    _write_json(_metadata_path(job_id), payload)
    return JobRecord(**payload)


def job_paths(job_id: str) -> tuple[Path, Path, Path]:
    return _task_path(job_id), _log_path(job_id), _exit_path(job_id)
