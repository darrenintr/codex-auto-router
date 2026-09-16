#!/usr/bin/env bash
set -euo pipefail

REPO="${CODEX_AUTO_REPO:-darrenintr/codex-auto-router}"
REPO_URL="https://github.com/${REPO}.git"
REPO_MAP_REPO="${CODEX_AUTO_REPO_MAP_REPO:-darrenintr/codex-repo-map}"
REPO_MAP_URL="https://github.com/${REPO_MAP_REPO}.git"
CLASSIFIER_MODE="${CODEX_AUTO_CLASSIFIER_MODE:-local}"
INSTALL_REPO_MAP="${CODEX_AUTO_INSTALL_REPO_MAP:-1}"
INSTALL_SHELL_ALIAS="${CODEX_AUTO_INSTALL_SHELL_ALIAS:-1}"
NONINTERACTIVE="${CODEX_AUTO_NONINTERACTIVE:-0}"
PROFILE="${CODEX_AUTO_TUNNEL_PROFILE:-codex-auto-router}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/codex-auto-router"
CONFIG_FILE="$CONFIG_DIR/config.toml"
ENV_FILE="$CONFIG_DIR/tunnel.env"
BIN_DIR="$HOME/.local/bin"
WORKSPACE="${CODEX_AUTO_WORKSPACE:-$HOME/Projects}"
MAX_REMOTE_TIER="${CODEX_AUTO_MAX_REMOTE_TIER:-terra_medium}"

if [[ -n "${CODEX_AUTO_SKIP_TUNNEL:-}" ]]; then
  SKIP_TUNNEL="$CODEX_AUTO_SKIP_TUNNEL"
elif [[ "$CLASSIFIER_MODE" == "chatgpt" ]]; then
  SKIP_TUNNEL=0
else
  SKIP_TUNNEL=1
fi

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
  local line='export PATH="$HOME/.local/bin:$PATH"' rc
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
    have apt-get || die "Install missing dependencies manually: ${missing[*]}"
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
  have codex-route || die "codex-route is not visible in PATH after installation"
}

install_repo_map() {
  if [[ "$INSTALL_REPO_MAP" != "1" ]]; then
    log "Repo Map installation skipped by CODEX_AUTO_INSTALL_REPO_MAP=$INSTALL_REPO_MAP"
    return
  fi
  log "Installing/updating codex-repo-map from $REPO_MAP_REPO"
  if ! pipx install --force "git+$REPO_MAP_URL"; then
    warn "Repo Map installation failed. Local classification still works with bounded read-only inspection."
    return
  fi
  if have codex-repo-map; then
    log "Repo Map found: $(command -v codex-repo-map)"
  else
    warn "codex-repo-map was installed but is not visible in PATH"
  fi
}

configure_router() {
  mkdir -p "$CONFIG_DIR" "$WORKSPACE"
  if [[ ! -f "$CONFIG_FILE" ]]; then
    codex-auto --init-config >/dev/null
  fi

  CONFIG_FILE="$CONFIG_FILE" CLASSIFIER_MODE="$CLASSIFIER_MODE" WORKSPACE="$WORKSPACE" MAX_REMOTE_TIER="$MAX_REMOTE_TIER" python3 - <<'PY'
from pathlib import Path
import json
import os
import re

p = Path(os.environ["CONFIG_FILE"])
text = p.read_text(encoding="utf-8")
mode = os.environ["CLASSIFIER_MODE"].strip().lower()
if mode not in {"local", "chatgpt", "heuristic"}:
    raise SystemExit("CODEX_AUTO_CLASSIFIER_MODE must be local, chatgpt, or heuristic")


def set_key(source: str, section: str, key: str, value: str, *, section_defaults: str = "") -> str:
    heading = f"[{section}]"
    if heading not in source:
        block = section_defaults.strip() or f"{heading}\n{key} = {value}"
        return source.rstrip() + "\n\n" + block + "\n"

    pattern = re.compile(rf"(?ms)^\[{re.escape(section)}\]\s*$.*?(?=^\[|\Z)")
    match = pattern.search(source)
    if not match:
        raise SystemExit(f"could not locate [{section}] in {p}")
    block = match.group(0)
    key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if key_pattern.search(block):
        block = key_pattern.sub(f"{key} = {value}", block, count=1)
    else:
        block = block.rstrip() + f"\n{key} = {value}\n"
    return source[: match.start()] + block + source[match.end() :]

classifier_defaults = '''[classifier]
mode = "local"
tier = "luna_low"
timeout_seconds = 120
fallback = "heuristic"
min_confidence = 0.80
repo_map_enabled = true
repo_map_binary = "codex-repo-map"
repo_map_budget = 2500
repo_map_timeout_seconds = 30
max_source_fallback_files = 3'''

text = set_key(text, "classifier", "mode", json.dumps(mode), section_defaults=classifier_defaults)
workspace = os.path.realpath(os.environ["WORKSPACE"])
text = set_key(text, "bridge", "default_workspace", json.dumps(workspace))
text = set_key(text, "bridge", "allowed_roots", f"[{json.dumps(workspace)}]")
text = set_key(text, "bridge", "max_remote_tier", json.dumps(os.environ["MAX_REMOTE_TIER"]))
p.write_text(text, encoding="utf-8")
PY

  log "Classifier mode: $CLASSIFIER_MODE"
  if [[ "$CLASSIFIER_MODE" == "local" ]]; then
    log "Local classifier: luna_low with Repo Map when available"
  fi
}

install_shell_alias() {
  if [[ "$INSTALL_SHELL_ALIAS" != "1" ]]; then
    log "Shell alias installation skipped"
    return
  fi
  local rc marker='# >>> codex-auto-router codex-first >>>'
  case "${SHELL:-}" in
    */zsh) rc="$HOME/.zshrc" ;;
    */fish)
      warn "Fish shell detected. Add manually: alias codex codex-route"
      return
      ;;
    *) rc="$HOME/.bashrc" ;;
  esac
  touch "$rc"
  if ! grep -Fq "$marker" "$rc" 2>/dev/null; then
    cat >> "$rc" <<'ALIAS_EOF'

# >>> codex-auto-router codex-first >>>
# Interactive shell only. Codex subcommands/options pass through unchanged.
alias codex='codex-route'
# <<< codex-auto-router codex-first <<<
ALIAS_EOF
  fi
  log "Installed transparent launcher alias in $rc"
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
    *) die "Unsupported CPU architecture: $(uname -m)" ;;
  esac
  [[ "$os" == "linux" ]] || die "Automatic tunnel-client installation currently supports Linux"

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
}

collect_tunnel_credentials() {
  TUNNEL_ID="${CONTROL_PLANE_TUNNEL_ID:-}"
  API_KEY="${CONTROL_PLANE_API_KEY:-}"
  if [[ (-z "$TUNNEL_ID" || -z "$API_KEY") && -r "$ENV_FILE" ]]; then
    TUNNEL_ID="${TUNNEL_ID:-$(grep -E '^CONTROL_PLANE_TUNNEL_ID=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)}"
    API_KEY="${API_KEY:-$(grep -E '^CONTROL_PLANE_API_KEY=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)}"
    [[ -n "$TUNNEL_ID" && -n "$API_KEY" ]] && log "Reusing saved Secure MCP Tunnel credentials"
  fi
  if [[ -z "$TUNNEL_ID" ]]; then
    open_url "https://platform.openai.com/settings/organization/tunnels"
    prompt TUNNEL_ID "Paste CONTROL_PLANE_TUNNEL_ID (tunnel_...): " || true
  fi
  if [[ -z "$API_KEY" ]]; then
    open_url "https://platform.openai.com/settings/organization/api-keys"
    prompt API_KEY "Paste CONTROL_PLANE_API_KEY (input hidden): " 1 || true
  fi
  [[ -n "$TUNNEL_ID" && -n "$API_KEY" ]] || return 1
  [[ "$TUNNEL_ID" == tunnel_* ]] || die "Tunnel ID must begin with tunnel_"
  export CONTROL_PLANE_TUNNEL_ID="$TUNNEL_ID"
  export CONTROL_PLANE_API_KEY="$API_KEY"
}

configure_tunnel() {
  local mcp_command
  mcp_command="$(command -v codex-auto-mcp)"
  tunnel-client init \
    --force \
    --sample sample_mcp_stdio_local \
    --profile "$PROFILE" \
    --tunnel-id "$TUNNEL_ID" \
    --mcp-command "$mcp_command"
  tunnel-client doctor --profile "$PROFILE" --health.listen-addr 127.0.0.1:0 --explain
  umask 077
  cat > "$ENV_FILE" <<ENV_EOF
CONTROL_PLANE_TUNNEL_ID=$TUNNEL_ID
CONTROL_PLANE_API_KEY=$API_KEY
ENV_EOF
  chmod 600 "$ENV_FILE"
}

install_systemd_service() {
  if ! have systemctl || ! systemctl --user show-environment >/dev/null 2>&1; then
    warn "systemd user services unavailable; run tunnel-client manually when using ChatGPT mode"
    return
  fi
  local unit_dir="$HOME/.config/systemd/user" unit="$HOME/.config/systemd/user/codex-auto-router.service" tunnel_bin
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
          *) warn "Automatic dependency installation is optimized for Ubuntu/Debian" ;;
        esac
      fi
      ;;
    Darwin) ;;
    *) die "Unsupported operating system: $(uname -s)" ;;
  esac

  install_codex
  install_router
  install_repo_map
  configure_router
  install_shell_alias

  if [[ "$SKIP_TUNNEL" == "1" ]]; then
    cat <<EOF

Setup complete.

Classifier mode: $CLASSIFIER_MODE
Repo Map: $(have codex-repo-map && echo enabled || echo unavailable)
Codex-first launcher: alias codex='codex-route'

Reload your shell, then use:
  source ~/.bashrc
  cd /path/to/project
  codex

In local mode, Luna Low classifies the task in a read-only Codex exec turn. Repo Map supplies compact project structure first; the selected tier is then launched in the same terminal.

The classifier prints its actual input/cached/output/reasoning token usage so routing overhead can be measured directly.

Use 'codex --direct' to bypass routing for one invocation.
To restore the v0.4 ChatGPT Web mode, set [classifier].mode = "chatgpt" and configure the optional tunnel.
EOF
    exit 0
  fi

  install_tunnel_client
  if collect_tunnel_credentials; then
    configure_tunnel
    install_systemd_service
    open_url "https://chatgpt.com/#settings/Connectors"
    cat <<EOF

Setup complete with optional ChatGPT Web routing.

Classifier mode: $CLASSIFIER_MODE
Tunnel profile: $PROFILE
Repo Map: $(have codex-repo-map && echo enabled || echo unavailable)

Reload your shell and run 'codex' from the exact project directory.
When classifier.mode = "chatgpt", send the generated handoff in ChatGPT Web with the Auto Router connector enabled.
EOF
  else
    warn "Tunnel credentials were not supplied. Local/heuristic routing remains usable."
  fi
}

main "$@"
