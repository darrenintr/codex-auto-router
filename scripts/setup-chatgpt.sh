#!/usr/bin/env bash
set -euo pipefail

PROFILE="${CODEX_AUTO_TUNNEL_PROFILE:-codex-auto-router}"
TUNNEL_ID="${1:-${CONTROL_PLANE_TUNNEL_ID:-}}"

if ! command -v codex >/dev/null 2>&1; then
  echo "error: Codex CLI was not found in PATH" >&2
  exit 1
fi

if ! command -v codex-auto-mcp >/dev/null 2>&1; then
  echo "error: codex-auto-mcp was not found. Install this project first: pipx install ." >&2
  exit 1
fi

if ! command -v tunnel-client >/dev/null 2>&1; then
  cat >&2 <<'EOF'
error: OpenAI tunnel-client was not found.
Install the supported Secure MCP Tunnel client from:
https://platform.openai.com/settings/organization/tunnels
EOF
  exit 1
fi

if [[ -z "$TUNNEL_ID" ]]; then
  cat <<'EOF'
A Secure MCP Tunnel ID is required for the one-time pairing.
Create or copy one from:
https://platform.openai.com/settings/organization/tunnels

Then run:
  ./scripts/setup-chatgpt.sh tunnel_...

The tunnel runtime also needs CONTROL_PLANE_API_KEY with Tunnels Read + Use permissions.
EOF
  exit 2
fi

MCP_COMMAND="$(command -v codex-auto-mcp)"

echo "[codex-auto-router] Initializing Secure MCP Tunnel profile: $PROFILE"
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile "$PROFILE" \
  --tunnel-id "$TUNNEL_ID" \
  --mcp-command "$MCP_COMMAND"

echo
echo "[codex-auto-router] Checking tunnel configuration..."
tunnel-client doctor --profile "$PROFILE" --explain

cat <<EOF

One-time local profile is ready.

Start the bridge in the foreground with:
  tunnel-client run --profile $PROFILE

Or use tunnel-client's managed runtime flow for a long-lived local connection:
  tunnel-client help plugin
  tunnel-client runtimes --help

While the tunnel is healthy, connect it in ChatGPT:
  https://chatgpt.com/#settings/Connectors

After the connector and Codex Auto Router plugin are installed, normal use is simply:
  @codex-auto-router <your coding task>
EOF
