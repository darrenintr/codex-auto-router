# codex-auto-router

Route **from Codex → ChatGPT Web → back to Codex** so the classification step does not consume a separate Codex turn.

The v0.4 flow starts in your terminal, where the current project is already known:

```text
$ cd /path/to/project
$ codex
› fix the animation regression
```

`codex-auto-router` captures the task plus current project/Git context, opens ChatGPT, and waits. In ChatGPT, send the handoff message (the installer/launcher copies it to your clipboard):

```text
@codex-auto-router route pending Codex request route_...
```

ChatGPT chooses the cheapest sufficient tier and submits only that route decision through the connected MCP bridge. The waiting terminal then resumes into the **real Codex CLI** with the selected model/reasoning effort and the original task.

> This project is an independent wrapper/integration for Codex CLI. It does not bypass, alter, or increase OpenAI account limits.

## Why Codex-first

Starting from Codex solves the project-context problem automatically. The router already knows:

- the current working directory,
- Git root,
- Git remote,
- current branch,
- changed/untracked file counts,
- approximate diff size,
- the exact task you typed.

That context is exposed to ChatGPT only through the narrow routing MCP tools, then the selected tier is written back to the waiting local launcher.

## Architecture

```text
Terminal / current project
        |
        |  codex
        |  task + cwd + git context
        v
codex-route
        |
        |  create pending route request
        |  open ChatGPT + wait
        v
ChatGPT Web
        |
        |  @codex-auto-router
        |  get_pending_codex_route()
        |  classify in ChatGPT
        |  submit_codex_route()
        v
codex-route (same terminal)
        |
        |  selected model + reasoning
        v
real Codex CLI
```

There is no ChatGPT webpage scraping, cookie reuse, or generic remote shell. Because ChatGPT does not expose a consumer-Web-chat API for an external local process to silently post a message into your conversation, the Web handoff still requires one explicit ChatGPT send action.

## One-command install

Ubuntu/Debian is the primary supported automatic setup path.

```bash
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

The installer automatically:

- installs missing Ubuntu/Debian dependencies,
- installs Codex CLI if necessary,
- installs/updates `codex-auto-router`,
- installs the Codex Auto Router marketplace/plugin,
- installs the `codex-route` launcher,
- adds `alias codex='codex-route'` to the interactive shell config,
- creates the router config,
- caps remote routing at `terra_medium` by default,
- installs/configures OpenAI Secure MCP Tunnel,
- creates a `systemd --user` service,
- opens the OpenAI tunnel/API-key pages when needed,
- opens ChatGPT Connector settings for the final account-side authorization.

After installation, open a new terminal or reload your shell config:

```bash
source ~/.bashrc
```

Then normal use is simply:

```bash
cd /path/to/project
codex
```

Enter your coding task. The router opens ChatGPT and waits for the route decision.

### Bypass routing for one invocation

```bash
codex --direct
```

Normal Codex subcommands/options are passed through automatically, for example:

```bash
codex plugin list
codex login
codex --model gpt-5.6-luna
```

## One-time ChatGPT pairing

The local machine still requires an explicitly authorized MCP connection. The installer handles the local pieces, but the OpenAI account/tunnel authorization must be approved by the user.

If you already have the tunnel credentials, setup can be non-interactive:

```bash
CONTROL_PLANE_TUNNEL_ID=tunnel_... \
CONTROL_PLANE_API_KEY=sk-... \
CODEX_AUTO_WORKSPACE="$HOME/Projects" \
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

Useful overrides:

```bash
CODEX_AUTO_MAX_REMOTE_TIER="terra_low"   # stricter route cap
CODEX_AUTO_SKIP_TUNNEL=1                  # local components only
CODEX_AUTO_INSTALL_SHELL_ALIAS=0          # do not replace interactive `codex`
CODEX_AUTO_NONINTERACTIVE=1               # never prompt on /dev/tty
```

## Daily Codex-first flow

1. `cd` into the project you want Codex to work on.
2. Run `codex`.
3. Type the task into the lightweight pre-router prompt.
4. ChatGPT opens automatically.
5. Send the copied `@codex-auto-router route pending Codex request ...` message.
6. ChatGPT reads the pending task/context, chooses a tier, and submits it.
7. The original terminal automatically turns into the real Codex TUI with the task already supplied.

The route request is stored locally under:

```text
~/.local/state/codex-auto-router/routes/
```

## Routing ladder

| Tier | Default model | Reasoning | Typical use |
| --- | --- | --- | --- |
| `luna_low` | `gpt-5.6-luna` | low | renames, tiny UI changes, localized edits |
| `luna_medium` | `gpt-5.6-luna` | medium | ordinary features and focused bug fixes |
| `terra_low` | `gpt-5.6-terra` | low | multi-file work and nontrivial debugging |
| `terra_medium` | `gpt-5.6-terra` | medium | subtle regressions, broad refactors, lifecycle/concurrency issues |
| `sol_medium` | `gpt-5.6-sol` | medium | unusually difficult architecture/debugging fallback |

Model availability can vary by account. All route mappings are configurable.

## Local safety controls

The MCP bridge exposes only scoped routing/dispatch tools:

- `get_pending_codex_route(request_id?)`
- `submit_codex_route(request_id, tier, reason?, confidence?)`
- `launch_codex(task, tier, workspace?)` for the older ChatGPT-first flow
- `get_codex_job(job_id)`
- `get_codex_log(job_id, lines?)`
- `cancel_codex_job(job_id)`

It does **not** expose arbitrary shell execution.

The local bridge enforces a tier cap:

```toml
[bridge]
max_remote_tier = "terra_medium"
```

So even if ChatGPT requests a stronger tier, the local bridge rejects it.

## ChatGPT handoff settings

```toml
[chatgpt]
url = "https://chatgpt.com/"
open_browser = true
copy_handoff = true
timeout_seconds = 300
fallback = "heuristic"   # heuristic | cancel
```

If ChatGPT does not submit a route before the timeout, the default behavior is to use the local heuristic router rather than block forever.

## CLI-only router

The original local router is still available:

```bash
codex-auto "fix the padding of the video card"
```

Preview a local route without launching Codex:

```bash
codex-auto --dry-run --explain \
  "refactor the shared-element transition and find the lifecycle regression"
```

## Plugin / Skill source

The ChatGPT-side component lives at:

```text
plugin/codex-auto-router/
```

The Skill is:

```text
plugin/codex-auto-router/skills/codex-auto-router/
```

When invoked for a pending Codex-first request, the Skill must use `get_pending_codex_route` + `submit_codex_route`; it must **not** call `launch_codex` for the same request, because the local launcher is already waiting to resume.

## Development

```bash
pip install -e '.[dev]'
pytest
python -m compileall -q src tests
bash -n install.sh scripts/setup-chatgpt.sh
```

## License

MIT
