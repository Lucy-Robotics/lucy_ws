#!/usr/bin/env bash
# CI smoke: tmux + pixi-wrapped core (headless sim) and control panel.
# Exercises the same tmux/pixi paths as launcher apply_changes without the TUI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Host tmux must not load Pixi's libtinfo (see launcher.tmux.HOST_TMUX).
host_tmux() { env -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH tmux "$@"; }

if ! command -v tmux >/dev/null 2>&1; then
  echo "ci_tmux_launcher_smoke: tmux not found" >&2
  exit 1
fi

if [[ ! -f "${ROOT}/install/setup.bash" ]]; then
  echo "ci_tmux_launcher_smoke: workspace not built" >&2
  exit 1
fi

printf 'DEV=true\n' > .env

export LUCY_WS_ROOT="$ROOT"
TMUX_SESSION="${LUCY_TMUX_SESSION:-lucy_ws}"
export LUCY_TMUX_SESSION="$TMUX_SESSION"

host_tmux start-server
host_tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
host_tmux new-session -d -s "$TMUX_SESSION" -n Lucy 'sleep 300'

pixi run -- python3 <<'PY'
import os

os.chdir(os.environ["LUCY_WS_ROOT"])
from launcher import (
    load_workspace_env,
    _tmux_new_pixi_window,
    run_shell_command,
)

load_workspace_env()

core_cmd = (
    "ros2 launch lucy_bringup lucy.launch.py "
    "robot_package:=inmoov_urdf gazebo:=true headless:=true"
)
run_shell_command(_tmux_new_pixi_window("core", core_cmd, remain_on_exit=True))
run_shell_command(
    _tmux_new_pixi_window("control_panel", "pixi run panel-dev", remain_on_exit=True)
)
PY

wait_for() {
  local pattern="$1"
  local label="$2"
  local timeout="${3:-180}"
  local elapsed=0
  while ! pgrep -f "$pattern" >/dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "ci_tmux_launcher_smoke: timeout waiting for ${label}" >&2
      host_tmux list-windows -t "$TMUX_SESSION" 2>/dev/null || true
      return 1
    fi
  done
  echo "ci_tmux_launcher_smoke: ${label} up (${elapsed}s)"
}

wait_for '[r]osbridge_websocket' 'rosbridge' 180
wait_for '[v]ite' 'control panel (vite)' 180

pixi run -- python3 <<'PY'
import os

os.chdir(os.environ["LUCY_WS_ROOT"])
from launcher import load_workspace_env, stop_all_packages, LauncherState, load_config

load_workspace_env()
stop_all_packages(LauncherState(load_config()))
PY

host_tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
echo "ci_tmux_launcher_smoke: OK"
