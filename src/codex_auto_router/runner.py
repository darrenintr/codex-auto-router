from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .config import load_config
from .external_provider import choose_external_model, load_external_config
from .jobs import get_job, job_paths


def build_codex_exec_command(record, config) -> list[str]:
    route = config.routes[record.tier]
    model = route.model
    model_provider: str | None = None

    external_config = load_external_config()
    external = choose_external_model(record.tier, external_config)
    if external is not None:
        model = external.model
        model_provider = external.codex_provider
    elif external_config.enabled and external_config.tier_models and external_config.tier_models.get(record.tier) and not external_config.fallback_official:
        raise RuntimeError(f"no external candidate for {record.tier} has usable capacity and fallback_official=false")

    command = [
        config.codex.binary,
        "exec",
        "--ephemeral",
        "--sandbox",
        config.bridge.sandbox,
        "--cd",
        record.workspace,
    ]
    if model_provider:
        command.extend(["-c", f'model_provider="{model_provider}"'])
    command.extend([
        "-c",
        f'model="{model}"',
        "-c",
        f'model_reasoning_effort="{route.effort}"',
    ])
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-auto-runner")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)

    config = load_config()
    record = get_job(args.job_id)
    task_path, log_path, exit_path = job_paths(args.job_id)
    task = task_path.read_text(encoding="utf-8")

    exit_code = 1
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"[codex-auto-router] job={record.job_id} tier={record.tier} model={record.model} effort={record.effort}\n")
        log.write(f"[codex-auto-router] workspace={record.workspace}\n\n")
        log.flush()
        try:
            command = [*build_codex_exec_command(record, config), task]
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
        except RuntimeError as exc:
            log.write(f"\n[codex-auto-router] provider routing stopped: {exc}\n")
            exit_code = 5
        except Exception as exc:  # pragma: no cover - defensive logging for detached worker
            log.write(f"\n[codex-auto-router] runner error: {type(exc).__name__}: {exc}\n")
            exit_code = 1

    exit_path.write_text(json.dumps({"exit_code": exit_code}), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
