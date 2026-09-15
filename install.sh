#!/usr/bin/env bash
set -euo pipefail

REPO="${CODEX_AUTO_REPO:-darrenintr/codex-auto-router}"
REPO_URL="https://github.com/${REPO}.git"
PROFILE="${CODEX_AUTO_TUNNEL_PROFILE:-codex-auto-router}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/codex-auto-router"
CONFIG_FILE="$CONFIG_DIR/config.toml"
ENV_FILE="$CONFIG_DIR/tunnel.env"
BIN_DIR="$HOME/.local/bin"
WORKSPACE="${CODEX_AUTO_WORKSPACE:-$HOME/Projects}"
MAX_REMOTE_TIER="${CODEX_AUTO_MAX_REMOTE_TIER:-terra_medium}"
SKIP_TUNNEL="${CODEX_AUTO_SKIP_TUNNEL:-0}"
NONINTERACTIVE="${CODEX_AUTO_NONINTERACTIVE:-0}"
# v0.4 is Codex-first but ChatGPT-routed. Installing the routing Skill inside
# Codex itself is opt-in because doing so spends Codex usage on classification.
INSTALL_CODEX_PLUGIN="${CODEX_AUTO_INSTALL_CODEX_PLUGIN:-0}"
REMOVE_LEGACY_CODEX_PLUGIN="${CODEX_AUTO_REMOVE_LEGACY_CODEX_PLUGIN:-1}"
INSTALL_SHELL_ALIAS="${CODEX_AUTO_INSTALL_SHELL_ALIAS:-1}"

log() { printf '\033[1;34m[codex-auto-router]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[codex-auto-router]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[codex-auto-router]\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

prompt() {
  local var_name="$1" message="$2" secret="${3:-0}" value=""
  if [[ "$NONINTERACTIVE" == "1" || ! -r /dev/tty ]]; then
    return 1
  fi
  if [[ "$secret" == "1" ]]; then
    printf '%s' "$message" > /dev/tty
    IFS= read -r -s value < /dev/tty || true
    printf '\n' > /dev/tty
  else
    printf '%s' "$message" > /dev/tty
    IFS= read -r value < /dev/tty || true
  fi
  printf -v "$var_name" '%s' "$value"
  [[ -n "$value" ]]
}

open_url() {
  local url="$1"
  if have xdg-open && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif have open; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

ensure_path() {
  mkdir -p "$BIN_DIR"
  export PATH="$BIN_DIR:$PATH"
  local line='export PATH="$HOME/.local/bin:$PATH"'
  local rc
  case "${SHELL:-}" in
    */zsh) rc="$HOME/.zshrc" ;;
    */fish) rc="" ;;
    *) rc="$HOME/.bashrc" ;;
  esac
  if [[ -n "$rc" ]]; then
    touch "$rc"
    grep -Fqx "$line" "$rc" 2>/dev/null || printf '\n%s\n' "$line" >> "$rc"
  fi
}

install_ubuntu_deps() {
  local missing=()
  for cmd in curl git unzip python3; do
    have "$cmd" || missing+=("$cmd")
  done
  have pipx || missing+=("pipx")
  if ! have node || ! have npm; then
    missing+=("nodejs" "npm")
  fi
  if (( ${#missing[@]} > 0 )); then
    have apt-get || die "This automatic dependency installer currently supports Ubuntu/Debian. Install manually: ${missing[*]}"
    log "Installing Ubuntu/Debian dependencies: ${missing[*]}"
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv pipx git curl unzip nodejs npm
  fi
}

install_codex() {
  if have codex; then
    log "Codex CLI found: $(command -v codex)"
    return
  fi
  have npm || die "npm is required to install Codex CLI"
  log "Installing official OpenAI Codex CLI into $HOME/.local"
  npm install -g --prefix "$HOME/.local" @openai/codex
  have codex || die "Codex installed but is not visible in PATH"
}

install_router() {
  have pipx || die "pipx is required"
  log "Installing/updating codex-auto-router from $REPO"
  pipx install --force "git+$REPO_URL"
  have codex-auto-mcp || die "codex-auto-mcp is not visible in PATH after installation"
  have codex-route || die "codex-route is not visible in PATH after installation"
}

codex_router_plugin_is_installed() {
  codex plugin list --json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
for item in data.get("installed", []):
    if item.get("name") == "codex-auto-router" and item.get("marketplaceName") == "codex-auto-router":
        raise SystemExit(0)
raise SystemExit(1)
'
}

remove_legacy_codex_plugin() {
  if [[ "$REMOVE_LEGACY_CODEX_PLUGIN" != "1" ]]; then
    return
  fi
  if ! codex plugin --help >/dev/null 2>&1; then
    return
  fi
  if codex_router_plugin_is_installed; then
    log "Removing legacy Codex-side Auto Router plugin"
    if codex plugin remove codex-auto-router@codex-auto-router >/dev/null 2>&1; then
      log "Removed Codex-side router. Routing @mentions belong in ChatGPT Web in v0.4+."
    else
      warn "Could not remove the legacy Codex-side plugin automatically."
      warn "Run: codex plugin remove codex-auto-router@codex-auto-router"
    fi
  fi
}

install_codex_plugin() {
  if [[ "$INSTALL_CODEX_PLUGIN" != "1" ]]; then
    log "Codex-side plugin is disabled by default; ChatGPT Web performs routing"
    return
  fi

  if ! codex plugin --help >/dev/null 2>&1; then
    warn "This Codex CLI build does not expose 'codex plugin'; skipping Codex-side @mention installation."
    return
  fi

  warn "Installing the Skill inside Codex is for debugging only; classification there consumes Codex usage."
  log "Adding Codex Auto Router marketplace to Codex"
  if ! codex plugin marketplace add "$REPO" --ref main >/dev/null; then
    warn "Could not add the Codex Auto Router marketplace automatically."
    warn "Run manually: codex plugin marketplace add $REPO --ref main"
    return
  fi

  if codex_router_plugin_is_installed; then
    log "Codex Auto Router plugin is already installed in Codex"
  else
    log "Installing Codex Auto Router plugin into Codex"
    if ! codex plugin add codex-auto-router@codex-auto-router; then
      warn "Marketplace was added, but the Codex plugin install failed."
      warn "Run manually: codex plugin add codex-auto-router@codex-auto-router"
      return
    fi
  fi

  log "Codex plugin registered for debugging. Restart any already-open Codex TUI."
}

install_shell_alias() {
  if [[ "$INSTALL_SHELL_ALIAS" != "1" ]]; then
    log "Shell alias installation skipped by CODEX_AUTO_INSTALL_SHELL_ALIAS=$INSTALL_SHELL_ALIAS"
    return
  fi

  local rc marker='# >>> codex-auto-router codex-first >>>'
  case "${SHELL:-}" in
    */zsh) rc="$HOME/.zshrc" ;;
    */fish)
      warn "Fish shell detected. Add this manually: alias codex codex-route"
      return
      ;;
    *) rc="$HOME/.bashrc" ;;
  esac

  touch "$rc"
  if ! grep -Fq "$marker" "$rc" 2>/dev/null; then
    cat >> "$rc" <<'ALIAS_EOF'

# >>> codex-auto-router codex-first >>>
# Interactive shell only. codex-route passes Codex subcommands/options through unchanged.
alias codex='codex-route'
# <<< codex-auto-router codex-first <<<
ALIAS_EOF
  fi
  log "Installed transparent Codex-first launcher alias in $rc"
}

configure_router() {
  mkdir -p "$CONFIG_DIR" "$WORKSPACE"
  if [[ ! -f "$CONFIG_FILE" ]]; then
    codex-auto --init-config >/dev/null
  fi
  CONFIG_FILE="$CONFIG_FILE" WORKSPACE="$WORKSPACE" MAX_REMOTE_TIER="$MAX_REMOTE_TIER" python3 - <<'PY'
from pathlib import Path
import json, os, re
p = Path(os.environ["CONFIG_FILE"])
text = p.read_text(encoding="utf-8")
workspace = os.path.realpath(os.environ["WORKSPACE"])
tier = os.environ["MAX_REMOTE_TIER"]
q = json.dumps(workspace)
replacements = {
    r'^default_workspace\s*=.*$': f'default_workspace = {q}',
    r'^allowed_roots\s*=.*$': f'allowed_roots = [{q}]',
    r'^max_remote_tier\s*=.*$': f'max_remote_tier = {json.dumps(tier)}',
}
for pattern, repl in replacements.items():
    text, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"could not update {pattern!r} in {p}")
p.write_text(text, encoding="utf-8")
PY
  log "ChatGPT-first fallback workspace: $WORKSPACE"
  log "Maximum remote tier: $MAX_REMOTE_TIER"
}

install_tunnel_client() {
  if have tunnel-client; then
    log "Secure MCP tunnel-client found: $(command -v tunnel-client)"
    return
  fi

  local os arch latest tag asset tmp binary
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$(uname -m)" in
    x86_64|amd64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) die "Unsupported CPU architecture for automatic tunnel-client install: $(uname -m)" ;;
  esac
  case "$os" in
    linux) ;;
    darwin)
      die "On macOS install the supported tunnel client with: brew install openai/tools/tunnel-client"
      ;;
    *) die "Automatic tunnel-client install currently supports Linux." ;;
  esac

  log "Finding the latest official OpenAI tunnel-client release"
  latest="$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/openai/tunnel-client/releases/latest)"
  tag="${latest##*/}"
  [[ "$tag" == v* ]] || die "Could not determine latest tunnel-client version"
  asset="https://github.com/openai/tunnel-client/releases/download/${tag}/tunnel-client-${tag}-linux-${arch}.zip"
  tmp="$(mktemp -d)"
  curl -fL "$asset" -o "$tmp/tunnel-client.zip"
  unzip -q "$tmp/tunnel-client.zip" -d "$tmp/unpacked"
  binary="$(find "$tmp/unpacked" -type f -name tunnel-client -print -quit)"
  [[ -n "$binary" ]] || die "Official release archive did not contain tunnel-client"
  install -m 0755 "$binary" "$BIN_DIR/tunnel-client"
  rm -rf "$tmp"
  log "Installed tunnel-client $tag"
}

collect_tunnel_credentials() {
  TUNNEL_ID="${CONTROL_PLANE_TUNNEL_ID:-}"
  API_KEY="${CONTROL_PLANE_API_KEY:-}"

  if [[ (-z "$TUNNEL_ID" || -z "$API_KEY") && -r "$ENV_FILE" ]]; then
    local saved_tunnel_id saved_api_key
    saved_tunnel_id="$(grep -E '^CONTROL_PLANE_TUNNEL_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
    saved_api_key="$(grep -E '^CONTROL_PLANE_API_KEY=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
    TUNNEL_ID="${TUNNEL_ID:-$saved_tunnel_id}"
    API_KEY="${API_KEY:-$saved_api_key}"
    if [[ -n "$TUNNEL_ID" && -n "$API_KEY" ]]; then
      log "Reusing saved Secure MCP Tunnel credentials from $ENV_FILE"
    fi
  fi

  if [[ -z "$TUNNEL_ID" ]]; then
    log "A one-time Secure MCP Tunnel ID is required. Opening the OpenAI Tunnels page."
    open_url "https://platform.openai.com/settings/organization/tunnels"
    prompt TUNNEL_ID "Paste CONTROL_PLANE_TUNNEL_ID (tunnel_...): " || true
  fi
  if [[ -z "$API_KEY" ]]; then
    log "A runtime API key with Tunnels Read + Use permissions is required. Opening the API keys page."
    open_url "https://platform.openai.com/settings/organization/api-keys"
    prompt API_KEY "Paste CONTROL_PLANE_API_KEY (input hidden): " 1 || true
  fi

  if [[ -z "$TUNNEL_ID" || -z "$API_KEY" ]]; then
    warn "Local installation is complete, but ChatGPT pairing was skipped because tunnel credentials were not supplied."
    warn "Re-run this same installer with CONTROL_PLANE_TUNNEL_ID and CONTROL_PLANE_API_KEY set to finish pairing."
    return 1
  fi
  [[ "$TUNNEL_ID" == tunnel_* ]] || die "Tunnel ID must begin with tunnel_"
  [[ "$API_KEY" != *$'\n'* && "$API_KEY" != *$'\r'* ]] || die "Invalid runtime API key"
  export CONTROL_PLANE_TUNNEL_ID="$TUNNEL_ID"
  export CONTROL_PLANE_API_KEY="$API_KEY"
}

configure_tunnel() {
  local mcp_command
  mcp_command="$(command -v codex-auto-mcp)"
  log "Creating/updating Secure MCP Tunnel profile: $PROFILE"
  tunnel-client init \
    --force \
    --sample sample_mcp_stdio_local \
    --profile "$PROFILE" \
    --tunnel-id "$TUNNEL_ID" \
    --mcp-command "$mcp_command"

  log "Validating tunnel configuration"
  tunnel-client doctor --profile "$PROFILE" --explain

  umask 077
  cat > "$ENV_FILE" <<ENV_EOF
CONTROL_PLANE_TUNNEL_ID=$TUNNEL_ID
CONTROL_PLANE_API_KEY=$API_KEY
ENV_EOF
  chmod 600 "$ENV_FILE"
}

install_systemd_service() {
  if ! have systemctl || ! systemctl --user show-environment >/dev/null 2>&1; then
    warn "systemd user services are unavailable. Start the tunnel manually with: tunnel-client run --profile $PROFILE"
    return
  fi
  local unit_dir="$HOME/.config/systemd/user"
  local unit="$unit_dir/codex-auto-router.service"
  local tunnel_bin
  tunnel_bin="$(command -v tunnel-client)"
  mkdir -p "$unit_dir"
  cat > "$unit" <<UNIT
[Unit]
Description=Codex Auto Router Secure MCP Tunnel
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
ExecStart=$tunnel_bin run --profile $PROFILE
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable codex-auto-router.service >/dev/null
  systemctl --user restart codex-auto-router.service
  if systemctl --user is-active --quiet codex-auto-router.service; then
    log "Background tunnel service is active"
  else
    warn "The service was installed but is not active. Check: journalctl --user -u codex-auto-router -n 100"
  fi
}

main() {
  log "One-command setup starting"
  ensure_path

  case "$(uname -s)" in
    Linux)
      if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        case "${ID:-}" in
          ubuntu|debian|linuxmint|pop) install_ubuntu_deps ;;
          *) warn "Detected ${ID:-Linux}; automatic package installation is optimized for Ubuntu/Debian." ;;
        esac
      fi
      ;;
    Darwin) ;;
    *) die "Unsupported operating system: $(uname -s)" ;;
  esac

  install_codex
  install_router
  remove_legacy_codex_plugin
  install_codex_plugin
  configure_router
  install_shell_alias

  if [[ "$SKIP_TUNNEL" == "1" ]]; then
    log "Tunnel setup skipped by CODEX_AUTO_SKIP_TUNNEL=1"
    exit 0
  fi

  install_tunnel_client
  if collect_tunnel_credentials; then
    configure_tunnel
    install_systemd_service
    open_url "https://chatgpt.com/#settings/Connectors"
    cat <<EOF

Setup complete.

ChatGPT-first fallback workspace: $WORKSPACE
Remote tier cap: $MAX_REMOTE_TIER
Tunnel profile: $PROFILE
Codex-first launcher: alias codex='codex-route'

Final account-side step:
  1. In ChatGPT Web, enable the tunnel-backed Codex Auto Router connector for the chat.
  2. Install/enable the Codex Auto Router Skill/Plugin in ChatGPT Web.
  3. Open a new terminal (or source your shell rc), cd into the exact project directory, and run: codex
  4. Enter the coding task. ChatGPT opens; send the copied @codex-auto-router handoff message there.
  5. ChatGPT submits the tier and the same terminal resumes into the real Codex CLI automatically.

IMPORTANT: do not type @codex-auto-router inside the Codex TUI. Routing must happen in ChatGPT Web; using the Skill inside Codex spends Codex usage and does not have the ChatGPT tunnel connector.

Use 'codex --direct' to bypass web routing for one invocation. Codex subcommands such as 'codex plugin list' are passed through automatically.

Service status:
  systemctl --user status codex-auto-router
EOF
  else
    cat <<EOF

Core installation complete.

The Codex-first shell alias is installed. Open a new terminal (or source your shell rc).
To finish ChatGPT pairing non-interactively, run the same one-command installer with:
  CONTROL_PLANE_TUNNEL_ID=tunnel_... CONTROL_PLANE_API_KEY=sk-... \
  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash
EOF
  fi
}

main "$@"
