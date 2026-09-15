# codex-auto-router

Route coding tasks from ChatGPT to the cheapest sufficient Codex tier, then start the task on your own machine.

The normal daily UX is intentionally small:

```text
@codex-auto-router fix the shared-element transition regression
```

ChatGPT classifies the task in the conversation, chooses a quota-conscious tier, and dispatches it through a tightly scoped local MCP bridge. **The routing decision does not require a separate Codex turn.** Only the actual Codex job uses Codex usage.

> This project is an independent wrapper/integration for Codex CLI. It does not bypass, alter, or increase OpenAI account limits.

## One-command install

Ubuntu/Debian is the primary supported automatic setup path.

```bash
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

The installer automatically:

- installs missing Ubuntu/Debian dependencies (`python3`, `pipx`, `git`, `curl`, `unzip`, Node/npm),
- installs Codex CLI if it is not already present,
- installs or updates `codex-auto-router`,
- creates the router config,
- defaults the allowed coding workspace to `~/Projects`,
- caps ChatGPT remote routing at `terra_medium`,
- downloads the latest official OpenAI Secure MCP `tunnel-client` release on Linux,
- creates and validates the tunnel profile,
- stores the runtime tunnel credentials in a user-only `0600` environment file,
- installs a `systemd --user` service so the bridge stays available after login,
- opens the OpenAI tunnel/API-key setup pages when credentials are needed,
- opens ChatGPT Connector settings for the final account-side authorization.

The OpenAI account authorization cannot safely be skipped by an installer. If the tunnel ID/API key are not supplied yet, the same installer completes the local part and tells you how to resume pairing.

For a non-interactive setup when you already have the tunnel credentials:

```bash
CONTROL_PLANE_TUNNEL_ID=tunnel_... \
CONTROL_PLANE_API_KEY=sk-... \
CODEX_AUTO_WORKSPACE="$HOME/Projects" \
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

Useful overrides:

```bash
CODEX_AUTO_WORKSPACE="$HOME/dev"              # allowed remote workspace
CODEX_AUTO_MAX_REMOTE_TIER="terra_low"        # stricter quota cap
CODEX_AUTO_SKIP_TUNNEL=1                       # install local router only
CODEX_AUTO_NONINTERACTIVE=1                    # never prompt on /dev/tty
```

After the one-time ChatGPT connector/plugin authorization, normal use is simply:

```text
@codex-auto-router implement the settings screen and run the focused tests
```

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

## Manual install

If you prefer not to use the installer, the local component requires Python 3.11+ and Codex CLI.

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

A Skill cannot directly grant itself permission to execute code on a user's laptop. The supported bridge is a local MCP server connected to ChatGPT through OpenAI Secure MCP Tunnel.

The one-command installer handles the local setup and tunnel profile. The user still has to explicitly create/authorize the OpenAI tunnel/runtime credential and enable the connector/plugin in ChatGPT.

Manual pairing remains available:

```bash
./scripts/setup-chatgpt.sh tunnel_...
```

Then either run the tunnel in the foreground:

```bash
tunnel-client run --profile codex-auto-router
```

or use the installed user service when configured by `install.sh`:

```bash
systemctl --user status codex-auto-router
journalctl --user -u codex-auto-router -n 100
```

See [`docs/secure-mcp-tunnel.md`](docs/secure-mcp-tunnel.md) for the complete setup.

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
default_workspace = "/home/you/Projects"
allowed_roots = ["/home/you/Projects"]
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

The CLI router's privacy-conscious history is stored separately at:

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
bash -n install.sh scripts/setup-chatgpt.sh
```

## License

MIT
