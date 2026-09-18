# codex-auto-router

Route a coding task to the cheapest sufficient Codex model/reasoning tier before the real task starts.

v0.5 adds a **local Codex classifier mode** and first-class [`codex-repo-map`](https://github.com/darrenintr/codex-repo-map) support. The default path is now:

```text
current project
     |
     | codex
     | task
     v
codex-route
     |
     +--> codex-repo-map
     |      incremental structural context
     |      ~1k-3k tokens instead of repo rediscovery
     |
     +--> Luna Low / read-only Codex classifier
     |      returns tier + confidence + usage
     |
     v
real Codex CLI
selected Luna / Terra / Sol tier
```

The older **Codex -> ChatGPT Web -> MCP -> Codex** route remains available as an optional compatibility mode.

> This project is an independent wrapper/integration for Codex CLI. It does not bypass, alter, or increase OpenAI account limits. A local Codex classifier turn consumes normal Codex usage, so the launcher prints the classifier's actual token usage for measurement.

## Why Repo Map

A cheap classifier is only useful if it does not have to rediscover the repository on every task.

Without Repo Map:

```text
Task -> Luna Low -> ls/rg/read files -> understand project -> choose tier
```

With Repo Map:

```text
Git + manifests + symbols + imports
              |
              v
      persistent local index
              |
Task ----------+----> compact context
                        |
                        v
                     Luna Low
                        |
                        v
                   choose tier
```

Repo Map stores its index under the target repository's `.git/codex-repo-map/` directory. It can refresh incrementally without sending source to a model.

If the compact map is insufficient, the Luna classifier runs in a **read-only sandbox** and is instructed to inspect only a small number of `source_fallback` files before making the route decision.

## One-command install

Ubuntu/Debian is the primary automatic setup path:

```bash
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

The installer now defaults to `classifier.mode = "local"` and installs/updates both:

- `codex-auto-router`
- `codex-repo-map`

It also installs the transparent shell launcher:

```bash
alias codex='codex-route'
```

After installation:

```bash
source ~/.bashrc
cd /path/to/project
codex
```

Enter the task at the lightweight pre-router prompt. The router builds a compact Repo Map context, runs the Luna Low classifier, prints its usage, and then replaces the current process with the real Codex CLI using the selected model and effort.

Typical output:

```text
› fix the fullscreen-to-inline return animation flicker
[codex-auto-router] Repo Map context ready (~1180 tokens)
[codex-auto-router] classifying locally with gpt-5.6-luna/low
[codex-auto-router] local classifier selected terra_low (confidence 0.91) — Cross-module lifecycle debugging.
[codex-auto-router] classifier usage: input=9124, cached=4096, output=43, reasoning=18
```

### Bypass routing for one invocation

```bash
codex --direct
```

Normal Codex subcommands/options still pass through automatically:

```bash
codex plugin list
codex login
codex --model gpt-5.6-luna
```

## Classifier modes

The main mode switch lives in `~/.config/codex-auto-router/config.toml`:

```toml
[classifier]
mode = "local"               # local | chatgpt | heuristic
tier = "luna_low"            # model/effort used for classification
timeout_seconds = 120
fallback = "heuristic"       # heuristic | cancel
min_confidence = 0.80

repo_map_enabled = true
repo_map_binary = "codex-repo-map"
repo_map_budget = 2500
repo_map_timeout_seconds = 30
max_source_fallback_files = 3
```

### `local` — default

Runs a small Codex classification turn in the **same project root** using the configured classifier tier, normally `luna_low`.

The classifier:

- receives the user's exact task;
- receives Repo Map's task-specific structural context;
- runs with `--sandbox read-only`;
- must not solve the task, modify files, build, test, or use the network;
- may inspect only a bounded number of source fallback files when the map is insufficient;
- returns one tier, a confidence value, and one short reason.

If confidence is below `min_confidence`, the launcher raises the selected tier by one step, capped by `routing.max_auto_tier`.

If the local classifier fails and `fallback = "heuristic"`, routing continues with the zero-model local heuristic.

### `heuristic`

No model classifier is used. The original deterministic task/Git heuristic picks a tier immediately.

### `chatgpt`

Preserves the v0.4 flow:

```text
codex-route
  -> pending route request
  -> ChatGPT Web Skill + MCP connector
  -> submit_codex_route
  -> same terminal launches real Codex
```

This mode requires the optional Secure MCP Tunnel setup. To make the installer configure it:

```bash
CODEX_AUTO_CLASSIFIER_MODE=chatgpt \
CODEX_AUTO_SKIP_TUNNEL=0 \
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

Local mode does **not** require ChatGPT Web, a connector, a Skill, or a tunnel.

## External API providers

Auto Router can optionally use [`codex-api-provider`](https://github.com/darrenintr/codex-api-provider) after the normal classifier chooses a tier. The classifier still decides the required capability; external models are explicit candidates for that tier and are filtered by availability, free/paid metadata and quota state.

Install and start the local gateway:

```bash
pipx install git+https://github.com/darrenintr/codex-api-provider.git
codex-api-provider init
codex-api-provider serve
```

Add the gateway to `~/.codex/config.toml`:

```toml
[model_providers.external]
name = "codex-api-provider"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"
```

Then copy `external.example.toml` to `~/.config/codex-auto-router/external.toml`, enable it, and map the tiers you want to external candidates. The router can prefer free models, reject exhausted or low-capacity providers, ignore stale observed rate limits, estimate a conservative token budget from USD credit plus model pricing, and fall back to the original official GPT route.

See [External provider routing](docs/external-provider-routing.md) for the full configuration and quota semantics.

## Repo Map integration contract

Auto Router calls:

```bash
codex-repo-map context . \
  --budget 2500 \
  --json
```

and sends the task on stdin. Repo Map refreshes its incremental index first and returns `schema_version: 1` JSON.

The router deliberately treats Repo Map as an optimization rather than a hard dependency. If the binary is missing, the index fails, or a non-supported repository is used, Luna falls back to bounded read-only inspection instead of blocking routing.

The task is removed from the Repo Map payload before the classifier prompt so it is not paid for twice.

## Routing ladder

| Tier | Default model | Reasoning | Typical use |
| --- | --- | --- | --- |
| `luna_low` | `gpt-5.6-luna` | low | renames, tiny UI changes, deterministic local edits |
| `luna_medium` | `gpt-5.6-luna` | medium | ordinary features and focused bug fixes |
| `terra_low` | `gpt-5.6-terra` | low | multi-file work and nontrivial debugging |
| `terra_medium` | `gpt-5.6-terra` | medium | subtle regressions, broad refactors, lifecycle/concurrency issues |
| `sol_medium` | `gpt-5.6-sol` | medium | unusually difficult architecture/debugging |

Local automatic routing is capped by:

```toml
[routing]
max_auto_tier = "sol_medium"
```

The ChatGPT/MCP path separately keeps its remote safety cap:

```toml
[bridge]
max_remote_tier = "terra_medium"
```

## Measuring classifier overhead

Every successful local classifier turn prints Codex's `turn.completed` usage:

```text
input=...
cached=...
output=...
reasoning=...
```

This makes it possible to benchmark real routing overhead instead of estimating it from prompt length.

A useful comparison is the same set of real tasks with:

```toml
repo_map_enabled = true
```

versus:

```toml
repo_map_enabled = false
```

The target is to reduce repeated repository-discovery input while keeping route decisions stable.

## Repo Map standalone

Install/update manually:

```bash
pipx install --force git+https://github.com/darrenintr/codex-repo-map.git
```

Inspect a project directly:

```bash
cd /path/to/project
codex-repo-map init .
codex-repo-map stats --json
codex-repo-map context --task "fix transition flicker" --budget 2500 --json
```

## Existing v0.4 installations

Upgrading is enough:

```bash
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
source ~/.bashrc
```

Existing config files without a `[classifier]` section still load safely: v0.5 defaults them to local classification. The installer also adds the new classifier section when needed.

Existing tunnel credentials and the MCP service can remain installed; local mode simply does not need them.

## ChatGPT/MCP tools

When `classifier.mode = "chatgpt"`, the bridge still exposes:

- `get_pending_codex_route(request_id?)`
- `submit_codex_route(request_id, tier, reason?, confidence?)`
- `launch_codex(task, tier, workspace?)`
- `get_codex_job(job_id)`
- `get_codex_log(job_id, lines?)`
- `cancel_codex_job(job_id)`

There is no generic remote shell tool.

## Legacy CLI router

The original explicit CLI remains available:

```bash
codex-auto --dry-run --explain "fix the padding of the video card"
```

Its existing `heuristic`, `ollama`, and `hybrid` scoring strategies remain separate from the transparent v0.5 `codex-route` classifier modes.

## Development

```bash
pip install -e '.[dev]'
pytest
python -m compileall -q src tests
bash -n install.sh scripts/setup-chatgpt.sh
```

## License

MIT
