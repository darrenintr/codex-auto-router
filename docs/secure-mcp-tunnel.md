# One-time Secure MCP Tunnel setup

This connects the local `codex-auto-mcp` stdio server to ChatGPT without opening a public inbound port on the machine.

## Prerequisites

- Codex CLI installed and authenticated.
- `codex-auto-router` installed (`pipx install .` or `uv tool install .`).
- OpenAI's supported `tunnel-client` installed from the Tunnels management page.
- A Secure MCP Tunnel ID.
- A runtime API key with Tunnels Read + Use permissions.

OpenAI setup pages:

- Tunnels: `https://platform.openai.com/settings/organization/tunnels`
- Runtime API keys: `https://platform.openai.com/settings/organization/api-keys`
- ChatGPT connectors: `https://chatgpt.com/#settings/Connectors`

## Configure the local router first

```bash
codex-auto --init-config
```

Edit `~/.config/codex-auto-router/config.toml` and set the workspace policy, for example:

```toml
[bridge]
default_workspace = "/home/darren/Projects"
allowed_roots = ["/home/darren/Projects", "/home/darren/Downloads"]
max_remote_tier = "terra_medium"
max_task_chars = 20000
sandbox = "workspace-write"
```

Keep `allowed_roots` narrow. The MCP bridge refuses paths outside these roots.

## Initialize the tunnel profile

Export the runtime API key in your shell:

```bash
export CONTROL_PLANE_API_KEY='...'
```

Then, from the repository checkout:

```bash
./scripts/setup-chatgpt.sh tunnel_...
```

The script uses OpenAI's stdio-local sample and points it at the installed `codex-auto-mcp` command. It then runs `tunnel-client doctor --explain`.

Equivalent manual setup:

```bash
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile codex-auto-router \
  --tunnel-id tunnel_... \
  --mcp-command "$(command -v codex-auto-mcp)"

tunnel-client doctor --profile codex-auto-router --explain
```

## Run it

For an attached foreground process:

```bash
tunnel-client run --profile codex-auto-router
```

For a long-lived runtime, use the managed runtime commands exposed by your installed tunnel-client instead of `nohup`/`disown`:

```bash
tunnel-client help plugin
tunnel-client runtimes --help
```

Verify the managed runtime reports running/healthy/ready before relying on it.

## Connect ChatGPT

While the tunnel is healthy, open ChatGPT connector settings and add/verify the tunnel-backed MCP app. Then install or enable the `codex-auto-router` Plugin/Skill for the workspace.

The app supplies the MCP tools; the Skill supplies the routing policy. They are intentionally separate so a Plugin install cannot silently authorize local code execution.

## Use

```text
@codex-auto-router
Fix the shared element transition regression on Android and iPad. Find the root cause, keep the change focused, and run targeted tests.
```

Expected behavior:

```text
→ Terra Medium · job_ab12...
```

The Codex process starts locally. Ask ChatGPT for the job status/log only when you need it.

## Troubleshooting

Check the local MCP server itself:

```bash
codex-auto-mcp
```

It will wait on stdio; Ctrl+C exits. For the actual bridge, normally let `tunnel-client` spawn it.

Check tunnel diagnostics:

```bash
tunnel-client doctor --profile codex-auto-router --explain
```

If ChatGPT cannot see the tools, keep the tunnel running and re-check the connector in ChatGPT settings.
