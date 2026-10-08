#!/usr/bin/env bash
# Start the Lucy stack (ROS 2 Jazzy + Control Center launcher) via Pixi.
#
# Prerequisite: python3 install.py
#
# Usage:
#   ./launch_lucy.sh                tmux + Control Center launcher (default)
#   ./launch_lucy.sh --headless <cmd>  run a single command, e.g. ros2 doctor --report
#   ./launch_lucy.sh --shell          interactive pixi shell (ros2 launch hints)
#
# Dev mode (DEV=true in env or .env): drop into an interactive Jazzy shell with the control
# panel running in background; you launch the ROS stack yourself (handy commands are printed).
#
# Ports published on the host: rosbridge 9090, control panel PORT_CONTROL_PANEL (defaults to
# VITE_PORT from src/lucy_control_panel/.env, else 4004). Vite proxies /rosbridge to the bridge.
#

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer user-local Pixi (official installer) over distro/nix packages.
export PATH="${HOME}/.pixi/bin:${PATH}"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

# Delegates to scripts/port_open.sh so this and the launcher readiness probes
# share one implementation. That also covers the case this used to miss:
# Debian-family bash is sometimes built without net redirections, where the
# /dev/tcp fallback fails exactly like a closed port, and every candidate port
# would look free.
host_port_in_use() {
  bash "${SCRIPT_DIR}/scripts/port_open.sh" "$1"
}

resolve_host_port() {
  local label="$1"
  local p="$2"
  local limit=$((p + 50))
  while [ "$p" -le "$limit" ]; do
    if ! host_port_in_use "$p"; then
      if [ "$p" != "$2" ]; then
        echo "Port $2 ($label) in use; using $p instead." >&2
      fi
      echo "$p"
      return 0
    fi
    p=$((p + 1))
  done
  echo "$2"
}

vite_listen_port_from_envfile() {
  local f="$SCRIPT_DIR/src/lucy_control_panel/.env"
  local raw val
  [[ -f "$f" ]] || return 1
  raw=$(grep -E '^[[:space:]]*VITE_PORT[[:space:]]*=' "$f" | tail -1 2>/dev/null || true)
  [[ -n "$raw" ]] || return 1
  val="${raw#*=}"
  val="${val#"${val%%[![:space:]]*}"}"
  val="${val%"${val##*[![:space:]]}"}"
  val="${val//\"/}"
  val="${val//\'/}"
  [[ "$val" =~ ^[0-9]+$ ]] || return 1
  echo "$val"
}

vite_scheme_from_envfile() {
  local f="$SCRIPT_DIR/src/lucy_control_panel/.env"
  local raw val
  [[ -f "$f" ]] || { echo "http"; return; }
  raw=$(grep -E '^[[:space:]]*VITE_HTTPS[[:space:]]*=' "$f" | tail -1 2>/dev/null || true)
  val="${raw#*=}"
  val="${val#"${val%%[![:space:]]*}"}"
  val="${val%"${val##*[![:space:]]}"}"
  val="${val//\"/}"
  val="${val//\'/}"
  if [[ "$(echo "$val" | tr '[:upper:]' '[:lower:]')" == "true" ]]; then
    echo "https"
  else
    echo "http"
  fi
}

check_cmd pixi

if [[ ! -f "$SCRIPT_DIR/install/setup.bash" && ! -f "$SCRIPT_DIR/install/setup.bat" ]]; then
  echo "Workspace not built. Run python3 install.py or Install in Lucy.py" >&2
  exit 1
fi

PORT_CONTROL_PANEL_CONTAINER="${PORT_CONTROL_PANEL_CONTAINER:-}"
if [[ -z "$PORT_CONTROL_PANEL_CONTAINER" ]]; then
  if v="$(vite_listen_port_from_envfile)"; then
    PORT_CONTROL_PANEL_CONTAINER="$v"
  else
    PORT_CONTROL_PANEL_CONTAINER=4004
  fi
fi
PORT_CONTROL_PANEL="$(resolve_host_port 'control panel' "${PORT_CONTROL_PANEL:-$PORT_CONTROL_PANEL_CONTAINER}")"
LCP_SCHEME="${LUCY_LCP_SCHEME:-$(vite_scheme_from_envfile)}"

export LUCY_LCP_PUBLISHED_HOST_PORT="$PORT_CONTROL_PANEL"
export LUCY_LCP_CONTAINER_PORT="$PORT_CONTROL_PANEL_CONTAINER"
export LUCY_LCP_SCHEME="$LCP_SCHEME"

echo "Control panel: ${LCP_SCHEME}://localhost:${PORT_CONTROL_PANEL}"

case "${1:-}" in
  --headless)
    shift
    if [ $# -eq 0 ]; then
      set -- ros2 doctor --report
    fi
    exec pixi run -- "$@"
    ;;
  --shell)
    exec bash "${SCRIPT_DIR}/scripts/pixi_dev_shell.sh"
    ;;
esac

# tmux is a host tool (not in Pixi). Session runs on the host; launcher runs in pixi run.
# Clear Pixi's LD_LIBRARY_PATH so system tmux does not load conda libtinfo.
TMUX_SESSION="${LUCY_TMUX_SESSION:-lucy_ws}"
case "$(uname -s)" in
  Linux|Darwin)
    if command -v tmux >/dev/null 2>&1; then
      LAUNCH_CMD="cd \"${SCRIPT_DIR}\" && pixi run -- python -m launcher"
      export LUCY_TMUX_SESSION="$TMUX_SESSION"
      # Package windows keep the session alive after the Control Center exits, so
      # "session exists" does not imply "Lucy window exists".
      exec bash -c "
        set -e
        host_tmux() { env -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH tmux \"\$@\"; }
        host_tmux start-server
        if ! host_tmux has-session -t ${TMUX_SESSION} 2>/dev/null; then
          host_tmux new-session -d -s ${TMUX_SESSION} -n Lucy \"${LAUNCH_CMD}\"
        elif ! host_tmux list-windows -t ${TMUX_SESSION} -F '#{window_name}' | grep -qx Lucy; then
          host_tmux new-window -t ${TMUX_SESSION} -n Lucy \"${LAUNCH_CMD}\"
        fi
        host_tmux select-window -t ${TMUX_SESSION}:Lucy 2>/dev/null || true
        host_tmux attach-session -t ${TMUX_SESSION}
      "
    fi
    echo "tmux not found — install tmux for the multi-window launcher (see README)." >&2
    exit 1
    ;;
esac

# Git Bash / MSYS on Windows: no tmux — run the Control Center launcher directly.
exec pixi run -- python -m launcher
