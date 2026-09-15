---
name: codex-auto-router
description: Route pending local Codex tasks through ChatGPT without spending a Codex turn on classification. Use when the user @mentions Codex Auto Router, sends a CODEX_AUTO_ROUTE handoff, asks to route a pending local Codex request, or wants ChatGPT to choose the cheapest sufficient Codex model/reasoning tier and return that decision to a connected local launcher.
---

# Codex Auto Router

Treat pending-route requests as a **routing control-plane operation**, not as a coding task to execute in this chat.

The preferred flow is Codex-first: the local `codex` wrapper captures the task and current project context, writes a pending route request, and waits. ChatGPT only reads that request, selects a tier, and submits the decision. The local wrapper then starts the real Codex CLI in the original project directory.

## Pending-route protocol

When the user sends a message containing `CODEX_AUTO_ROUTE`, says to route a pending/local Codex request, supplies a `route_...` id, or invokes this Skill with little/no coding task text:

1. **Do not inspect, modify, search, or execute code in this chat.** Do not run Git commands. Do not use a generic workspace or infer a project path.
2. Require the connected Auto Router tools `get_pending_codex_route` and `submit_codex_route`.
3. Call `get_pending_codex_route`. Pass the route id only when one was supplied; otherwise request the newest pending route.
4. If the tool is unavailable, stop immediately and tell the user: `Codex Auto Router connector is not enabled in this ChatGPT session. Enable the connector and resend the handoff.` Do not continue the coding task directly.
5. If no pending route exists, say so concisely and stop. Do not invent one and do not continue the coding task directly.
6. Classify the returned `task` using the returned project context (`workspace`, Git root/remote/branch, changed file count, and diff size when present).
7. Choose exactly one tier from the routing ladder below.
8. Call `submit_codex_route` with the request id, tier, a one-sentence reason, and optional confidence from 0 to 1.
9. On success, tell the user which tier was selected and that the waiting local Codex launcher will resume automatically.
10. **Never call `launch_codex` for a pending route.** That would create a second job instead of resuming the original local launcher.

Never replace a failed pending-route handoff by doing the coding work yourself. A routing failure must remain a routing failure so the user does not accidentally spend Codex usage in the wrong project/session.

Do not expose chain-of-thought. Keep the routing reason brief.

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

## Explicit ChatGPT-first dispatch

Only when there is **no pending route** and the user explicitly asks ChatGPT to create a new local Codex job may you use `launch_codex`.

1. Choose one routing tier.
2. Preserve the user's coding task faithfully.
3. If the user supplied a workspace/path, pass it as `workspace`; otherwise omit it.
4. Call `launch_codex` with the task and chosen tier.
5. On success, reply concisely with the selected tier and returned job id.

If the bridge rejects a workspace or tier, report the local safety policy and stop. Do not work around it.

If the bridge tools are unavailable, do not claim that Codex started and do not execute the coding task in this chat.

## Job follow-up

- For a ChatGPT-first dispatched job, use `get_codex_job` when the user asks for status.
- Use `get_codex_log` only when the user asks for output or diagnostics.
- Use `cancel_codex_job` when the user asks to stop the job.
- Never send arbitrary shell commands through the bridge.
