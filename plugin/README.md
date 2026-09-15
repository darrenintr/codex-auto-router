# ChatGPT Plugin component

This directory contains the ChatGPT-side routing component for `codex-auto-router`.

The first version is intentionally **skill-only**: ChatGPT classifies the coding task in the conversation and returns a local `codex-auto --force-tier ...` command. No OpenAI API key is needed for classification, and the classifier does not call Codex.

## Why skill-only first

A ChatGPT Plugin can package skills and apps. For quota routing, the model already has enough information to choose the tier, so an external app would add complexity without improving the classification itself.

This also avoids unsupported automation of the ChatGPT website. The local CLI remains responsible for launching Codex.

## Fully automatic local hand-off

A later optional MCP bridge can let ChatGPT send the selected route to a local machine through a supported remote MCP connection / Secure MCP Tunnel. That is separate from the classifier and should be opt-in because it can trigger local actions.

## Local CLI hand-off

Single-line task:

```bash
codex-auto --force-tier luna_medium "implement the settings screen"
```

Multi-line task:

```bash
codex-auto --force-tier terra_low --stdin <<'CODEX_TASK'
Investigate the Android build regression.
Keep the change minimal and run the targeted tests.
CODEX_TASK
```
