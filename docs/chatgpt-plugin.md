# ChatGPT Plugin architecture

`codex-auto-router` v0.3 uses ChatGPT itself as the routing classifier and a local, narrowly scoped MCP server for execution.

## Daily flow

```text
User in ChatGPT
  @codex-auto-router <coding task>
          |
          v
Skill chooses cheapest sufficient tier
          |
          v
launch_codex(task, tier, workspace?)
          |
          v
Secure MCP Tunnel
          |
          v
local codex-auto-mcp
          |
          v
codex exec
```

The routing classification happens in the normal ChatGPT conversation. It does not launch a second Codex task just to decide which Codex tier to use.

## Why the bridge exists

A Skill is instructions, not a background agent with direct access to a user's laptop. Starting a local Codex process is an external action, so the Plugin uses a connected MCP app.

ChatGPT cannot directly dial an arbitrary localhost MCP endpoint. The supported design uses OpenAI Secure MCP Tunnel to expose the local MCP server through an OpenAI-hosted tunnel endpoint while keeping the local server off the public internet.

## Skill behavior

The Skill:

1. Classifies the engineering complexity.
2. Prefers the cheapest sufficient tier.
3. Calls `launch_codex` when the connected local bridge is available.
4. Reports only the selected tier and job id unless more detail is requested.
5. Uses `get_codex_job`, `get_codex_log`, or `cancel_codex_job` only for explicit follow-up requests.

If the bridge is not connected, the Skill must not pretend a local Codex job started. It falls back to a ready-to-run `codex-auto --force-tier ...` command.

## MCP surface

The server intentionally does not expose a generic command runner.

### `launch_codex`

Inputs:

```text
task: string
tier: luna_low | luna_medium | terra_low | terra_medium | sol_medium
workspace?: string
```

Local validation checks:

- task is non-empty and below `max_task_chars`;
- tier does not exceed `max_remote_tier`;
- workspace exists and is within `default_workspace` / `allowed_roots`;
- Codex is launched with the configured sandbox.

The server creates a detached local worker and returns a job id quickly rather than holding the ChatGPT MCP request open for the whole coding task.

### `get_codex_job`

Returns job metadata/status.

### `get_codex_log`

Returns a bounded log tail for user-requested diagnostics.

### `cancel_codex_job`

Stops the detached job process.

## Why there is still one-time setup

Installing a Skill/Plugin cannot silently grant ChatGPT permission to execute processes on an arbitrary laptop. The local bridge and tunnel must be explicitly installed/authorized once.

After that pairing, the intended normal UX is only:

```text
@codex-auto-router <task>
```

See [`secure-mcp-tunnel.md`](secure-mcp-tunnel.md).
