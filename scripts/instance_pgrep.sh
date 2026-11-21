#!/usr/bin/env bash
# pgrep restricted to this Control Center's stack.
#
#   scripts/instance_pgrep.sh <pgrep args...>     e.g. -f '[r]osbridge_websocket'
#
# Prints the matching pids and exits 0 when there is at least one, like pgrep.
#
# Several launchers can run side by side (lucy_ws_0, lucy_ws_1, ...; see
# launcher/instance.py), each with its own rosbridge, controller_manager, Gazebo.
# A bare pgrep in a readiness check or a teardown would see the other stack's
# processes. Each process carries LUCY_TMUX_SESSION from the window that started
# it; one without it (started by hand) belongs to the default session, lucy_ws_0.

set -uo pipefail

session="${LUCY_TMUX_SESSION:-lucy_ws_0}"

# Sets `owner` to the session of pid $1. Builtins only on Linux: this runs for
# every match of every readiness check the launcher polls.
session_of() {
  local kv entry
  owner=""
  if [[ -r "/proc/$1/environ" ]]; then
    while IFS= read -r -d '' kv; do
      if [[ "${kv}" == LUCY_TMUX_SESSION=* ]]; then
        owner="${kv#*=}"
        break
      fi
    done < "/proc/$1/environ" 2>/dev/null
  elif [[ "${OSTYPE}" == darwin* ]]; then
    # ps eww appends the environment to the command line (own processes only).
    for entry in $(ps eww -o command= -p "$1" 2>/dev/null); do
      if [[ "${entry}" == LUCY_TMUX_SESSION=* ]]; then
        owner="${entry#*=}"
        break
      fi
    done
  fi
  owner="${owner:-lucy_ws_0}"
}

pids=$(pgrep "$@") || exit 1
found=1
for pid in ${pids}; do
  # pgrep skips itself but not this script, whose argv holds the pattern.
  [[ "${pid}" == "$$" ]] && continue
  session_of "${pid}"
  if [[ "${owner}" == "${session}" ]]; then
    echo "${pid}"
    found=0
  fi
done
exit "${found}"
