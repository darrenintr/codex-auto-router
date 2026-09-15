# ChatGPT Plugin architecture

`codex-auto-router` v0.4 uses ChatGPT as the routing classifier while preserving the local Codex working directory that the user started from.

## Primary daily flow: Codex-first

```text
User in terminal / current project
  codex
  > coding task
          |
          v
codex-route creates a pending request
(task + cwd + Git context)
          |
          v
ChatGPT Web
  @codex-auto-router route pending Codex request route_...
          |
          v
get_pending_codex_route(request_id)
          |
          v
Skill chooses cheapest sufficient tier
          |
          v
submit_codex_route(request_id, tier, ...)
          |
          v
same waiting terminal resumes
          |
          v
real Codex CLI starts with selected model/reasoning
```

The classification happens in the normal ChatGPT conversation. No Codex task is started until the route decision has come back to the local launcher.

## Why the bridge exists

A Skill is instructions, not a background agent with direct access to a user's laptop. Reading a pending local route request and writing the decision back are external actions, so the Plugin uses a connected MCP app.

ChatGPT cannot directly dial an arbitrary localhost MCP endpoint. The supported design uses OpenAI Secure MCP Tunnel to expose the local MCP server through an OpenAI-hosted tunnel endpoint while keeping the local server off the public internet.

## Skill behavior

For a pending Codex-first request, the Skill must:

1. Call `get_pending_codex_route` (with the explicit route id if supplied, otherwise the newest pending request).
2. Classify the returned task using the attached project/Git context.
3. Prefer the cheapest sufficient tier.
4. Call `submit_codex_route`.
5. Stop there. **Do not call `launch_codex` for the same request**; the local launcher is already waiting and will start Codex itself.

If there is no pending request and the user explicitly asks ChatGPT to start a new job, the older ChatGPT-first `launch_codex` flow remains supported.

## MCP surface

The server intentionally does not expose a generic command runner.

### `get_pending_codex_route`

Inputs:

```text
request_id?: string
```

Returns the task plus local project context:

```text
request_id
status
task
workspace
repo_root?
repo_remote?
branch?
changed_files
untracked_files
diff_lines
```

When no id is passed, the newest pending request is returned.

### `submit_codex_route`

Inputs:

```text
request_id: string
tier: luna_low | luna_medium | terra_low | terra_medium | sol_medium
reason?: string
confidence?: number (0..1)
```

The local bridge validates `max_remote_tier` before accepting the decision. On success, the waiting `codex-route` process notices the updated request and replaces itself with the real Codex CLI.

### `launch_codex`

Retained for ChatGPT-first dispatches where no local launcher is waiting.

### `get_codex_job` / `get_codex_log` / `cancel_codex_job`

Follow-up tools for ChatGPT-first detached jobs.

## Local request state

Pending route requests are stored locally under:

```text
~/.local/state/codex-auto-router/routes/
```

Each request is a small JSON record. The task remains on the user's machine until ChatGPT retrieves it through the explicitly connected MCP bridge.

## Why one ChatGPT send action remains

The project intentionally does not scrape ChatGPT, reuse browser cookies, or automate the consumer web UI. A local process cannot silently post into a normal ChatGPT Web conversation through a supported consumer API.

Therefore `codex-route` opens ChatGPT and copies a message such as:

```text
@codex-auto-router route pending Codex request route_1234...
```

The user explicitly sends that message. After that, the route returns automatically and the terminal resumes into Codex.

## One-time setup

Installing a Skill/Plugin cannot silently grant ChatGPT permission to access a laptop. The local bridge and Secure MCP Tunnel must be explicitly installed/authorized once.

See [`secure-mcp-tunnel.md`](secure-mcp-tunnel.md).
