# codex-auto-router

Route coding tasks from ChatGPT to the cheapest sufficient Codex tier, then start the task on your own machine.

The v0.3 flow is designed around a simple daily UX:

```text
@codex-auto-router fix the shared-element transition regression
```

ChatGPT classifies the task in the conversation, chooses a tier, and dispatches it through a tightly scoped local MCP bridge. **The routing decision does not require a separate Codex turn.** Only the Codex job itself uses Codex usage.

> This project is an independent wrapper/integration for Codex CLI. It does not bypass, alter, or increase OpenAI account limits.

## Architecture

```text
ChatGPT Web
    |
    |  @codex-auto-router
    |  classify task in ChatGPT
    v
luna_low / luna_medium / terra_low / terra_medium / sol_medium
    |
    |  launch_codex MCP tool
    v
OpenAI Secure MCP Tunnel
    |
    v
codex-auto-mcp (your machine)
    |
    |  validates tier + workspace + task length
    v
codex exec --sandbox workspace-write ...
```

There is no ChatGPT webpage scraping, cookie reuse, or generic remote shell.

## Routing ladder

| Tier | Default model | Reasoning | Typical use |
| --- | --- | --- | --- |
| `luna_low` | `gpt-5.6-luna` | low | renames, tiny UI changes, localized edits |
| `luna_medium` | `gpt-5.6-luna` | medium | ordinary features and focused bug fixes |
| `terra_low` | `gpt-5.6-terra` | low | multi-file work and nontrivial debugging |
| `terra_medium` | `gpt-5.6-terra` | medium | subtle regressions, broad refactors, lifecycle/concurrency issues |
| `sol_medium` | `gpt-5.6-sol` | medium | unusually difficult architecture/debugging fallback |

Model availability can vary by account. All routes are configurable.

## Install the local component

Requires Python 3.11+ and Codex CLI.

```bash
git clone https://github.com/darrenintr/codex-auto-router.git
cd codex-auto-router
pipx install .
codex-auto --init-config
```

Or with `uv`:

```bash
uv tool install .
codex-auto --init-config
```

The config is stored at:

```text
~/.config/codex-auto-router/config.toml
```

## One-time ChatGPT pairing

A Skill cannot directly execute shell commands on a user's laptop. The supported bridge is a local MCP server connected to ChatGPT through OpenAI Secure MCP Tunnel.

1. Install the supported `tunnel-client` from OpenAI's Tunnels settings page.
2. Create a tunnel and runtime API key with Tunnels Read + Use permissions.
3. Export the runtime key as `CONTROL_PLANE_API_KEY`.
4. Run:

```bash
./scripts/setup-chatgpt.sh tunnel_...
```

5. Start the tunnel profile:

```bash
tunnel-client run --profile codex-auto-router
```

6. While it is healthy, add the tunnel as a ChatGPT connector/app in ChatGPT settings and install the Codex Auto Router plugin from this repository/workspace marketplace.

See [`docs/secure-mcp-tunnel.md`](docs/secure-mcp-tunnel.md) for the complete setup and the managed-runtime option.

After this one-time pairing, normal use is:

```text
@codex-auto-router implement the settings screen and run the focused tests
```

If the connected `launch_codex` tool is available, the Skill dispatches automatically instead of asking you to copy a terminal command.

## Local safety controls

The bridge intentionally exposes only four tools:

- `launch_codex(task, tier, workspace?)`
- `get_codex_job(job_id)`
- `get_codex_log(job_id, lines?)`
- `cancel_codex_job(job_id)`

It does **not** accept arbitrary shell commands.

Configure remote limits:

```toml
[bridge]
default_workspace = "/home/you/projects"
allowed_roots = ["/home/you/projects"]
max_remote_tier = "terra_medium"
max_task_chars = 20000
sandbox = "workspace-write"
```

Remote dispatches are rejected when they exceed `max_remote_tier` or target a path outside the allowed roots.

## CLI-only mode

The original local router remains available even without ChatGPT:

```bash
codex-auto "fix the padding of the video card"
```

Preview the route without launching Codex:

```bash
codex-auto --dry-run --explain \
  "refactor the shared-element transition and find the lifecycle regression"
```

Force a route:

```bash
codex-auto --force-tier terra_low "investigate the Android build regression"
```

Multi-line input:

```bash
codex-auto --force-tier terra_low --stdin <<'CODEX_TASK'
Investigate the Android build regression.
Keep the change minimal and run targeted tests.
CODEX_TASK
```

## Optional local classifier

CLI-only routing defaults to deterministic heuristics. It can optionally use Ollama:

```bash
ollama pull qwen3:1.7b
```

Then:

```toml
[routing]
strategy = "hybrid"
ollama_model = "qwen3:1.7b"
```

This local classifier is separate from the ChatGPT Plugin flow.

## Job state

Remote-dispatched jobs are stored under:

```text
~/.local/state/codex-auto-router/jobs/
```

Each job keeps metadata, its task, a Codex log, and exit status locally.

The CLI router's privacy-conscious history is still stored separately at:

```text
~/.local/state/codex-auto-router/history.jsonl
```

History stores a SHA-256 hash and routing metadata rather than prompt contents.

## Plugin / Skill source

The ChatGPT-side component lives at:

```text
plugin/codex-auto-router/
```

The standalone Skill is:

```text
plugin/codex-auto-router/skills/codex-auto-router/
```

See [`docs/chatgpt-plugin.md`](docs/chatgpt-plugin.md) for the dispatch behavior.

## Development

```bash
pip install -e '.[dev]'
pytest
python -m compileall -q src tests
```

## License

MIT
