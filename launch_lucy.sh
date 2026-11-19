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

# Control Center instance. A launcher already shown in a terminal belongs to
# someone: another ./launch_lucy.sh starts a second instance beside it instead of
# joining it, in tmux session lucy_ws_<n>, with rosbridge and control panel ports
# shifted by <n> and the next free ROS domain (picked by the launcher, see
# launcher/instance.py). A detached instance is re-attached. LUCY_TMUX_SESSION
# pins the session.
#
# Lucy runs on its own tmux server, on <state root>/tmux.sock (same root as
# launcher/constants.py state_root()): a plain "tmux ls" never shows Lucy, other
# users / checkouts / CI runs do not collide with it, and each LUCY_STATE_DIR gets
# its own server. Every instance (lucy_ws_<n>) lives on the server of its root.
STATE_ROOT="${LUCY_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/lucy}"
TMUX_SOCKET="${STATE_ROOT}/tmux.sock"

pick_tmux_session() {
  local n=0 s
  while (( n <= 100 )); do
    s="lucy_ws_${n}"
    # "=" asks tmux for this exact name: a bare lucy_ws_1 also matches lucy_ws_10.
    if ! tmux -S "$TMUX_SOCKET" list-windows -t "=${s}" -F '#{window_name}' 2>/dev/null | grep -qx Lucy \
      || [[ "$(tmux -S "$TMUX_SOCKET" display-message -p -t "=${s}:" '#{session_attached}' 2>/dev/null)" == 0 ]]; then
      echo "${s}"
      return
    fi
    n=$((n + 1))
  done
  echo "lucy_ws_${n}"
}

TMUX_SESSION="lucy_ws_0"
INSTANCE=0
case "${1:-}" in
  --headless|--shell) ;;
  *)
    if command -v tmux >/dev/null 2>&1; then
      TMUX_SESSION="${LUCY_TMUX_SESSION:-$(pick_tmux_session)}"
      [[ "${TMUX_SESSION}" =~ ^lucy_ws_([0-9]+)$ ]] && INSTANCE="${BASH_REMATCH[1]}"
      mkdir -p -m 700 "${STATE_ROOT}"
      export LUCY_TMUX_SOCKET="$TMUX_SOCKET"
      # A unix socket path is limited to ~104 bytes (sun_path).
      if (( ${#TMUX_SOCKET} > 100 )); then
        echo "Warning: tmux socket path is ${#TMUX_SOCKET} chars (limit ~104); tmux may fail. Set a shorter LUCY_STATE_DIR." >&2
      fi
    fi
    ;;
esac

PORT_CONTROL_PANEL_CONTAINER="${PORT_CONTROL_PANEL_CONTAINER:-}"
if [[ -z "$PORT_CONTROL_PANEL_CONTAINER" ]]; then
  if v="$(vite_listen_port_from_envfile)"; then
    PORT_CONTROL_PANEL_CONTAINER="$v"
  else
    PORT_CONTROL_PANEL_CONTAINER=4004
  fi
fi
PORT_CONTROL_PANEL="$(resolve_host_port 'control panel' "$(( ${PORT_CONTROL_PANEL:-$PORT_CONTROL_PANEL_CONTAINER} + INSTANCE ))")"
# rosbridge falls back to a free port itself; this keeps instances off each other's.
PORT_ROSBRIDGE="$(( ${PORT_ROSBRIDGE:-9090} + INSTANCE ))"
LCP_SCHEME="${LUCY_LCP_SCHEME:-$(vite_scheme_from_envfile)}"

export LUCY_LCP_PUBLISHED_HOST_PORT="$PORT_CONTROL_PANEL"
export LUCY_LCP_CONTAINER_PORT="$PORT_CONTROL_PANEL_CONTAINER"
export LUCY_LCP_SCHEME="$LCP_SCHEME"
export PORT_ROSBRIDGE

if (( INSTANCE > 0 )); then
  echo "Lucy instance ${INSTANCE}: tmux session ${TMUX_SESSION}, rosbridge port ${PORT_ROSBRIDGE}"
fi
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
case "$(uname -s)" in
  Linux|Darwin)
    if command -v tmux >/dev/null 2>&1; then
      export LUCY_TMUX_SESSION="$TMUX_SESSION"
      # Passed on the command line: a session created on a running tmux server
      # starts from the server's environment, i.e. the first instance's.
      INSTANCE_ENV="LUCY_TMUX_SESSION=${TMUX_SESSION} PORT_ROSBRIDGE=${PORT_ROSBRIDGE}"
      INSTANCE_ENV+=" LUCY_LCP_PUBLISHED_HOST_PORT=${LUCY_LCP_PUBLISHED_HOST_PORT}"
      INSTANCE_ENV+=" LUCY_LCP_CONTAINER_PORT=${LUCY_LCP_CONTAINER_PORT} LUCY_LCP_SCHEME=${LUCY_LCP_SCHEME}"
      INSTANCE_ENV+=" LUCY_TMUX_SOCKET=$(printf '%q' "$TMUX_SOCKET")"
      [[ -n "${LUCY_STATE_DIR:-}" ]] && INSTANCE_ENV+=" LUCY_STATE_DIR=$(printf '%q' "$LUCY_STATE_DIR")"
      LAUNCH_CMD="cd $(printf '%q' "$SCRIPT_DIR") && env ${INSTANCE_ENV} pixi run -- python -m launcher"
      # Package windows keep the session alive after the Control Center exits, so
      # "session exists" does not imply "Lucy window exists". The socket, session
      # and command reach the inner shell through its environment (paths may
      # contain spaces). TMUX is cleared on attach so this also works from inside
      # the user's own tmux.
      export LAUNCH_CMD SCRIPT_DIR
      exec bash -c '
        set -e
        T=(tmux -S "$LUCY_TMUX_SOCKET")
        "${T[@]}" start-server
        if ! "${T[@]}" has-session -t "=${LUCY_TMUX_SESSION}" 2>/dev/null; then
          "${T[@]}" new-session -d -s "${LUCY_TMUX_SESSION}" -n Lucy "${LAUNCH_CMD}"
        elif ! "${T[@]}" list-windows -t "=${LUCY_TMUX_SESSION}" -F "#{window_name}" | grep -qx Lucy; then
          "${T[@]}" new-window -t "=${LUCY_TMUX_SESSION}:" -n Lucy "${LAUNCH_CMD}"
        fi
        bash "${SCRIPT_DIR}/scripts/tmux_theme.sh" "${LUCY_TMUX_SESSION}" || true
        "${T[@]}" select-window -t "=${LUCY_TMUX_SESSION}:Lucy" 2>/dev/null || true
        TMUX= "${T[@]}" attach-session -t "=${LUCY_TMUX_SESSION}"
      '
    fi
    echo "tmux not found — install tmux for the multi-window launcher (see README)." >&2
    exit 1
    ;;
esac

# Git Bash / MSYS on Windows: no tmux — run the Control Center launcher directly.
exec pixi run -- python -m launcher
