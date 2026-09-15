---
name: codex-auto-router
description: Route a coding task to the cheapest sufficient Codex model/reasoning tier and emit a ready-to-run local codex-auto command. Use when the user wants to save Codex quota, choose a Codex tier, or send a coding task to Codex efficiently.
---

# Codex Auto Router

Classify the user's coding task inside ChatGPT, then hand the decision to the local `codex-auto` CLI. The classification itself should not invoke Codex.

## Goal

Choose the cheapest tier that is likely to complete the task reliably. Do not select a stronger tier merely because the prompt is long or detailed.

## Routing ladder

Use these tiers, from cheapest to strongest:

1. `luna_low` — trivial/localized edits, renames, formatting, tiny UI tweaks, simple lookups.
2. `luna_medium` — ordinary features, straightforward bug fixes, routine tests, focused UI work.
3. `terra_low` — multi-file changes, nontrivial debugging, build failures, moderate refactors.
4. `terra_medium` — subtle regressions, lifecycle/rendering/concurrency problems, broad refactors or migrations.
5. `sol_medium` — unusually difficult architecture or debugging that clearly exceeds Terra.

Default to `luna_low` or `luna_medium`. Prefer Terra only when there is concrete complexity. Treat `sol_medium` as a fallback, not a default.

Never invent an Astra tier. Do not automatically route above `terra_medium` unless the user explicitly asks for the strongest route or the task has unusually difficult architecture/debugging requirements.

## Classification signals

Consider the actual engineering work required, including:

- Number of subsystems or files likely to be involved.
- Whether the root cause is unknown.
- Cross-platform behavior.
- Lifecycle, rendering, concurrency, race-condition, memory, security, or performance complexity.
- Architecture changes, migrations, or repository-wide refactors.
- Whether the task is a tiny deterministic edit.

Do not use verbosity alone as a complexity signal.

If repository context is not available, classify from the user's task only. Do not ask the user to paste an entire repository just to choose a tier.

## Output

Return a short result containing:

- Selected tier.
- One-sentence reason.
- A ready-to-run command.

For a one-line task, use:

```bash
codex-auto --force-tier <tier> "<task>"
```

For a multi-line task, use stdin mode:

```bash
codex-auto --force-tier <tier> --stdin <<'CODEX_TASK'
<task>
CODEX_TASK
```

Keep the explanation concise. Do not expose chain-of-thought or a long hidden scoring process.
