# ChatGPT Plugin component

This directory contains the ChatGPT-side component for `codex-auto-router` v0.3.

The Plugin's Skill classifies a coding task inside the ChatGPT conversation. When the separate local MCP app is connected through OpenAI Secure MCP Tunnel, it calls `launch_codex` directly and starts the selected Codex tier on the user's machine.

Normal usage after one-time pairing:

```text
@codex-auto-router fix this animation regression
```

No copy/paste hand-off is required when the bridge tool is connected.

## Why the MCP app is separate

A Plugin/Skill installation cannot silently authorize local process execution. The user's local `codex-auto-mcp` server must be explicitly connected once. This repository deliberately does not bundle a generic remote shell.

See:

- `../docs/chatgpt-plugin.md`
- `../docs/secure-mcp-tunnel.md`
