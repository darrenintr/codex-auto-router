# ChatGPT Plugin architecture

`codex-auto-router` can use ChatGPT itself as the routing classifier without scraping the ChatGPT website and without sending the classification task through Codex.

## Architecture

```text
ChatGPT conversation
      |
      |  Plugin skill classifies engineering complexity
      v
luna_low / luna_medium / terra_low / terra_medium / sol_medium
      |
      |  emits local hand-off command
      v
codex-auto --force-tier <tier> ...
      |
      v
Codex CLI
```

The classification and Codex execution are separate steps. Only the actual Codex execution uses Codex usage.

## Why this is preferable to browser scraping

Automating the consumer ChatGPT webpage as an unofficial API is brittle and is not the supported integration path. Modern ChatGPT Plugins can contain reusable skills, and Apps SDK / MCP can be added when an external action is actually required.

## Phase 1: skill-only

The included `plugin/codex-auto-router/SKILL.md` tells ChatGPT how to choose the cheapest sufficient route and produce a `codex-auto` command. This requires no additional backend.

## Phase 2: optional MCP bridge

For users who want one-click hand-off from ChatGPT to a local development machine, add an MCP app with a tightly scoped tool such as:

```text
prepare_codex_route(task, tier)
```

The tool should validate the tier against the local config and create a one-time route ticket. A local `codex-auto` process can consume that ticket. Avoid exposing a generic shell-execution tool.

ChatGPT cannot directly connect to an arbitrary localhost MCP server. Use the supported remote MCP path or Secure MCP Tunnel where available.

## Security constraints for a future bridge

- Accept only known routing tiers.
- Never expose arbitrary shell execution.
- Keep actual Codex invocation opt-in.
- Require confirmation for actions that start a local coding task.
- Do not transmit repository contents unless the user explicitly requests it.
