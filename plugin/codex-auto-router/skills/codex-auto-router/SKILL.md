---
name: codex-auto-router
description: Route coding tasks from ChatGPT to a connected local Codex CLI using the cheapest sufficient model/reasoning tier. Use when the user @mentions Codex Auto Router, asks ChatGPT to start or hand off a coding task to Codex, wants to save Codex quota, or asks which Codex tier should handle a coding task.
---

# Codex Auto Router

Classify the coding task in ChatGPT, then dispatch it through the connected local Codex Auto Router MCP app when that tool is available. The classification step must not start a separate Codex task.

## Routing ladder

Choose the cheapest tier likely to complete the task reliably:

1. `luna_low` — deterministic local edits, renames, formatting, tiny UI tweaks.
2. `luna_medium` — normal features, focused bug fixes, routine tests and UI work.
3. `terra_low` — multi-file work, build failures, nontrivial debugging, moderate refactors.
4. `terra_medium` — subtle regressions, lifecycle/rendering/concurrency issues, broad refactors or migrations.
5. `sol_medium` — unusually difficult architecture/debugging only.

Default to Luna. Use Terra only for concrete complexity. Do not choose a tier merely because the prompt is long. Never invent an Astra tier.

Unless the user explicitly requests a stronger route, do not choose above `terra_medium`. The local bridge applies its own hard maximum tier regardless of this instruction.

## Classify

Consider:

- likely file/subsystem scope;
- whether the root cause is unknown;
- cross-platform behavior;
- lifecycle, rendering, concurrency, race-condition, memory, security, or performance complexity;
- architecture changes, migrations, or repository-wide refactors;
- whether the requested change is small and deterministic.

Do not expose chain-of-thought. Keep the user-facing reason to one sentence at most.

## Dispatch

If the connected app exposes `launch_codex`:

1. Choose one routing tier.
2. Preserve the user's coding task faithfully; do not expand it into unrelated work.
3. If the user supplied a workspace/path, pass it as `workspace`. Otherwise omit it so the local configured default is used.
4. Call `launch_codex` with the task and chosen tier.
5. On success, reply concisely with the selected tier and returned job id. Do not ask the user to copy a shell command.

If the bridge rejects a workspace or tier, report that local safety policy blocked the dispatch. Do not work around the restriction.

If `launch_codex` is not available, do not claim that Codex started. Tell the user the one-time local bridge connection is not active and provide this fallback command:

```bash
codex-auto --force-tier <tier> --stdin <<'CODEX_TASK'
<task>
CODEX_TASK
```

## Job follow-up

- When the user asks whether a dispatched job is still running, call `get_codex_job`.
- When the user asks what Codex is doing, why it failed, or requests output, call `get_codex_log`. Avoid repeatedly polling logs without a user request.
- When the user asks to stop a job, call `cancel_codex_job`.
- Never send arbitrary shell commands through the bridge; the bridge is intentionally limited to Codex task dispatch.
