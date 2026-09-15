from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .config import load_config
from .jobs import get_job, job_paths


def build_codex_exec_command(record, config) -> list[str]:
    route = config.routes[record.tier]
    return [
        config.codex.binary,
        "exec",
        "--ephemeral",
        "--sandbox",
        config.bridge.sandbox,
        "--cd",
        record.workspace,
        "-c",
        f'model="{route.model}"',
        "-c",
        f'model_reasoning_effort="{route.effort}"',
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-auto-runner")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)

    config = load_config()
    record = get_job(args.job_id)
    task_path, log_path, exit_path = job_paths(args.job_id)
    task = task_path.read_text(encoding="utf-8")
    command = [*build_codex_exec_command(record, config), task]

    exit_code = 1
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"[codex-auto-router] job={record.job_id} tier={record.tier} model={record.model} effort={record.effort}\n")
        log.write(f"[codex-auto-router] workspace={record.workspace}\n\n")
        log.flush()
        try:
            completed = subprocess.run(
                command,
                cwd=record.workspace,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            exit_code = completed.returncode
        except FileNotFoundError:
            log.write(f"\n[codex-auto-router] executable not found: {config.codex.binary}\n")
            exit_code = 127
        except Exception as exc:  # pragma: no cover - defensive logging for detached worker
            log.write(f"\n[codex-auto-router] runner error: {type(exc).__name__}: {exc}\n")
            exit_code = 1

    exit_path.write_text(json.dumps({"exit_code": exit_code}), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
