# codex-auto-router

A small, quota-conscious router for the OpenAI Codex CLI.

Instead of manually choosing a model and reasoning effort for every task, `codex-auto` estimates the engineering complexity of your prompt and current Git working tree, then launches Codex with a configurable model/reasoning tier.

> This project is an independent wrapper around Codex CLI. It does not bypass, alter, or increase account limits.

## Why

Using a high-cost model or high reasoning effort for every edit can burn through included Codex usage quickly. Most coding work does not need the strongest tier.

`codex-auto-router` defaults to a conservative ladder:

| Tier | Default model | Reasoning | Typical use |
| --- | --- | --- | --- |
| `luna_low` | `gpt-5.6-luna` | low | renames, tiny UI changes, localized edits |
| `luna_medium` | `gpt-5.6-luna` | medium | ordinary feature work and bug fixes |
| `terra_low` | `gpt-5.6-terra` | low | multi-file work and nontrivial debugging |
| `terra_medium` | `gpt-5.6-terra` | medium | complex regressions and broad refactors |
| `sol_medium` | `gpt-5.6-sol` | medium | difficult architecture/debugging fallback |

Model availability can vary by account. Every route is editable in `config.toml`.

## Features

- Zero runtime Python dependencies.
- Heuristic routing from task wording, task size, Git changed-file count, and diff size.
- Optional local Ollama classifier, so task classification does not consume Codex quota.
- Hybrid mode that combines deterministic heuristics with the local classifier.
- Hard maximum auto-tier to prevent accidental expensive routing.
- `--dry-run` and `--explain` modes.
- Privacy-conscious history: stores prompt hashes and routing metadata, not prompt contents.
- Pass-through arguments to the real Codex CLI.

## Install

Requires Python 3.11+ and the Codex CLI already installed.

With `pipx`:

```bash
pipx install .
```

With `uv`:

```bash
uv tool install .
```

For development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create your user config:

```bash
codex-auto --init-config
```

The config is written to:

```text
~/.config/codex-auto-router/config.toml
```

## Usage

```bash
codex-auto "fix the padding of the video card"
```

Inspect the choice without spending Codex quota:

```bash
codex-auto --dry-run --explain "refactor the shared-element transition and find the lifecycle regression"
```

Example output:

```text
[codex-auto] terra_low: gpt-5.6-terra / low (score=5, heuristic=5, strategy=heuristic)
```

Pass normal Codex CLI options after `--`:

```bash
codex-auto "fix the failing tests" -- --sandbox workspace-write
```

Force a tier when you already know what you want:

```bash
codex-auto --force-tier luna_low "rename this symbol"
```

## Publish this checkout to GitHub

If you downloaded the source archive instead of cloning an existing repo, the included helper can initialize Git, create the GitHub repository, add `origin`, and push `main`:

```bash
./scripts/publish-github.sh
```

It creates a public repository named `codex-auto-router` by default. To create it as private:

```bash
./scripts/publish-github.sh codex-auto-router --private
```

The helper requires the GitHub CLI (`gh`) to be installed and authenticated.

## Make it replace `codex`

After installing, add this to your shell configuration:

```bash
alias codex='codex-auto'
```

The wrapper launches the real Codex executable from `PATH`, so shell aliases do not cause recursion.

## ChatGPT Plugin routing

The repository also includes a ChatGPT-side router in [`plugin/codex-auto-router/SKILL.md`](plugin/codex-auto-router/SKILL.md). This lets ChatGPT classify the task in the conversation and hand the selected tier to the local CLI, so the **classification step itself does not use Codex quota**.

For example, the Plugin can return:

```bash
codex-auto --force-tier terra_low "investigate the Android build regression"
```

For multi-line tasks, `codex-auto` supports stdin:

```bash
codex-auto --force-tier terra_low --stdin <<'CODEX_TASK'
Investigate the Android build regression.
Keep the fix minimal and run targeted tests.
CODEX_TASK
```

This is deliberately not implemented by scraping the ChatGPT website. See [`docs/chatgpt-plugin.md`](docs/chatgpt-plugin.md) for the Plugin architecture and an optional future MCP bridge for automatic local hand-off.

## Local classifier with Ollama

Heuristics are the default and require nothing extra. If you want a smarter classifier, install Ollama and pull a small local model such as `qwen3:1.7b`:

```bash
ollama pull qwen3:1.7b
```

Then change:

```toml
[routing]
strategy = "hybrid"
ollama_model = "qwen3:1.7b"
```

`hybrid` gives the local classifier 65% of the final score and the deterministic heuristic 35%. If Ollama is unavailable, hybrid mode safely falls back to heuristics.

## Configuration

The generated config contains all routing thresholds and model mappings. The most important safety setting is:

```toml
max_auto_tier = "terra_medium"
```

For a very quota-conscious setup, use `terra_medium` or even `terra_low`. You can still override it manually with `--force-tier`.

The default configuration intentionally contains no automatic Astra tier. If you want an expensive model, invoke it manually or change a route yourself.

## How scoring works

The heuristic looks for signals such as:

- Prompt length and number of separate instructions.
- `refactor`, `migration`, `performance`, `security`, `root cause`, `lifecycle`, `concurrency`, and similar engineering terms.
- Current Git changed-file count.
- Current staged and unstaged diff size.
- Small-change signals such as `rename`, `typo`, and `one-line` reduce the score.

Repository dirtiness contributes at most two points, so an already-dirty working tree cannot by itself force an expensive model.

## Privacy

When history is enabled, the router writes metadata to:

```text
~/.local/state/codex-auto-router/history.jsonl
```

It stores a SHA-256 hash and length of the prompt, not the prompt itself. Disable it with:

```toml
save_history = false
```

## Development

```bash
pip install -e '.[dev]'
pytest
```

## License

MIT
