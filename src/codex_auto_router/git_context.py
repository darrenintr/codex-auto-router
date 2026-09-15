from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class GitContext:
    is_repo: bool = False
    changed_files: int = 0
    untracked_files: int = 0
    diff_lines: int = 0
    repo_root: str | None = None


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=3,
    )


def collect_git_context(cwd: Path | None = None) -> GitContext:
    cwd = cwd or Path.cwd()
    probe = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if probe.returncode != 0:
        return GitContext()

    root = probe.stdout.strip()
    status = _run_git(["status", "--porcelain"], cwd)
    lines = [line for line in status.stdout.splitlines() if line.strip()]
    changed = len(lines)
    untracked = sum(1 for line in lines if line.startswith("??"))

    # Count both staged and unstaged changes. This is deliberately approximate.
    unstaged = _run_git(["diff", "--numstat"], cwd)
    staged = _run_git(["diff", "--cached", "--numstat"], cwd)

    def count_numstat(text: str) -> int:
        total = 0
        for line in text.splitlines():
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            for value in parts[:2]:
                if value.isdigit():
                    total += int(value)
        return total

    diff_lines = count_numstat(unstaged.stdout) + count_numstat(staged.stdout)
    return GitContext(
        is_repo=True,
        changed_files=changed,
        untracked_files=untracked,
        diff_lines=diff_lines,
        repo_root=root or None,
    )
