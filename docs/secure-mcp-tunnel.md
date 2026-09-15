# One-time Secure MCP Tunnel setup

This connects the local `codex-auto-mcp` stdio server to ChatGPT without opening a public inbound port on the machine.

## Recommended: one-command setup

Ubuntu/Debian users should start with:

```bash
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

The installer handles the local dependencies, Codex/router installation, router config, official OpenAI `tunnel-client` download, tunnel profile, validation, and a `systemd --user` service. When tunnel credentials are missing it opens the OpenAI setup pages and prompts through `/dev/tty`, so `curl | bash` remains interactive.

If you already have a tunnel ID and runtime key, the whole local pairing can be non-interactive:

```bash
CONTROL_PLANE_TUNNEL_ID=tunnel_... \
CONTROL_PLANE_API_KEY=sk-... \
CODEX_AUTO_WORKSPACE="$HOME/Projects" \
curl -fsSL https://raw.githubusercontent.com/darrenintr/codex-auto-router/main/install.sh | bash
```

The account-side ChatGPT connector/plugin authorization still requires explicit user approval and is intentionally not bypassed.

## Manual prerequisites

- Codex CLI installed and authenticated.
- `codex-auto-router` installed (`pipx install .` or `uv tool install .`).
- OpenAI's supported `tunnel-client` installed from the Tunnels management page or official release.
- A Secure MCP Tunnel ID.
- A runtime API key with Tunnels Read + Use permissions.

OpenAI setup pages:

- Tunnels: `https://platform.openai.com/settings/organization/tunnels`
- Runtime API keys: `https://platform.openai.com/settings/organization/api-keys`
- ChatGPT connectors: `https://chatgpt.com/#settings/Connectors`

## Configure the local router manually

```bash
codex-auto --init-config
```

Edit `~/.config/codex-auto-router/config.toml` and set the workspace policy, for example:

```toml
[bridge]
default_workspace = "/home/you/Projects"
allowed_roots = ["/home/you/Projects"]
max_remote_tier = "terra_medium"
max_task_chars = 20000
sandbox = "workspace-write"
```

Keep `allowed_roots` narrow. The MCP bridge refuses paths outside these roots.

## Initialize the tunnel profile manually

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
  --tunnel-id tunnel_0123456789abcdef0123456789abcdef \
  --mcp-command "$(command -v codex-auto-mcp)"

tunnel-client doctor --profile codex-auto-router --explain
```

## Run it

The one-command installer creates and starts a user service on Ubuntu when systemd user services are available:

```bash
systemctl --user status codex-auto-router
journalctl --user -u codex-auto-router -n 100
```

For an attached foreground process instead:

```bash
tunnel-client run --profile codex-auto-router
```

For other managed-runtime deployments, use the native runtime commands exposed by your installed tunnel-client rather than `nohup`/`disown`:

```bash
tunnel-client help plugin
tunnel-client runtimes --help
```

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

Check the service installed by the one-command setup:

```bash
systemctl --user status codex-auto-router
journalctl --user -u codex-auto-router -n 100
```

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
