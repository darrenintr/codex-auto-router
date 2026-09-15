#!/usr/bin/env bash
set -euo pipefail

repo_name="${1:-codex-auto-router}"
visibility="${2:---public}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 127
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required: https://cli.github.com/" >&2
  exit 127
fi

gh auth status >/dev/null

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -b main
  git add .
  git commit -m "Initial release: quota-conscious Codex model router"
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "origin already exists: $(git remote get-url origin)" >&2
  echo "Refusing to create a second GitHub repository." >&2
  exit 2
fi

gh repo create "$repo_name" "$visibility" --source=. --remote=origin --push
