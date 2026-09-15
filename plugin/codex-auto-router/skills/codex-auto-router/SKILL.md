---
name: codex-auto-router
description: Route Codex coding tasks through ChatGPT without spending a separate Codex turn on classification. Use when the user @mentions Codex Auto Router, asks to route a pending local Codex task, wants ChatGPT to choose the cheapest sufficient Codex model/reasoning tier, or asks to hand a coding task to a connected local Codex CLI.
---

# Codex Auto Router

Prefer the **Codex-first** flow: a local `codex` launcher creates a pending route request containing the task and current project context, then ChatGPT classifies it and submits only the tier decision back. The waiting local launcher starts Codex after the decision, so classification itself does not start a Codex task.

## Codex-first flow

When the user says to route a pending/local Codex request, mentions a route id, or invokes this Skill with little/no task text:

1. Call `get_pending_codex_route`. Pass the route id only when the user supplied one; otherwise request the newest pending route.
2. If no pending route exists, say so concisely and do not invent one.
3. Classify the returned `task` using its project context (`workspace`, Git root/remote/branch, changed file count, and diff size when present).
4. Choose exactly one tier from the routing ladder below.
5. Call `submit_codex_route` with the request id, tier, a one-sentence reason, and optional confidence from 0 to 1.
6. On success, tell the user which tier was selected and that the waiting local Codex launcher will resume automatically.
7. **Do not call `launch_codex` for the same pending request.** That would duplicate the job and lose the Codex-first handoff semantics.

Do not expose chain-of-thought. The reason sent to the tool and shown to the user must be brief.

## Routing ladder

Choose the cheapest tier likely to complete the task reliably:

1. `luna_low` — deterministic local edits, renames, formatting, tiny UI tweaks.
2. `luna_medium` — normal features, focused bug fixes, routine tests and UI work.
3. `terra_low` — multi-file work, build failures, nontrivial debugging, moderate refactors.
4. `terra_medium` — subtle regressions, lifecycle/rendering/concurrency issues, broad refactors or migrations.
5. `sol_medium` — unusually difficult architecture/debugging only.

Default to Luna. Use Terra only for concrete complexity. Do not choose a tier merely because the prompt is long. Never invent an Astra tier.

Unless the user explicitly requests a stronger route, do not choose above `terra_medium`. The local bridge applies its own hard maximum tier regardless of this instruction.

## Classification signals

Consider:

- likely file/subsystem scope;
- whether the root cause is unknown;
- cross-platform behavior;
- lifecycle, rendering, concurrency, race-condition, memory, security, or performance complexity;
- architecture changes, migrations, or repository-wide refactors;
- whether the requested change is small and deterministic;
- current working-tree size only as supporting evidence, not as the main reason to escalate.

## ChatGPT-first fallback

If there is no pending route and the user explicitly asks ChatGPT to start a new local Codex job, use `launch_codex`:

1. Choose one routing tier.
2. Preserve the user's coding task faithfully; do not expand it into unrelated work.
3. If the user supplied a workspace/path, pass it as `workspace`. Otherwise omit it so the local configured default is used.
4. Call `launch_codex` with the task and chosen tier.
5. On success, reply concisely with the selected tier and returned job id.

If the bridge rejects a workspace or tier, report that local safety policy blocked the dispatch. Do not work around the restriction.

If neither the pending-route tools nor `launch_codex` are available, do not claim that Codex started. Tell the user the one-time local bridge connection is not active.

## Job follow-up

- When the user asks whether a ChatGPT-first dispatched job is still running, call `get_codex_job`.
- When the user asks what such a job is doing, why it failed, or requests output, call `get_codex_log`.
- When the user asks to stop such a job, call `cancel_codex_job`.
- Never send arbitrary shell commands through the bridge; the bridge is intentionally limited to Codex routing and task dispatch.
