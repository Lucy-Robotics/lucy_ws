#!/usr/bin/env bash
# Exit 0 when ros2_control reports at least `min_active` *active* controllers.
#
#   scripts/controllers_active.sh [min_active]
#
# min_active 0 asks only whether /controller_manager answered at all.
#
# Used by config/launcher_config.json so core reads ready only when the robot can
# actually be driven. Process liveness is not enough: controller_manager happily
# runs with every controller stuck `unconfigured`/`inactive` — which is exactly
# what a stale /robot_description or a held spawner lock produces — and the TUI
# would otherwise show a green [RUNNING] next to a robot that cannot move.
#
# Two costs to contain:
#   * `ros2 control list_controllers` needs a full Pixi activation, far too slow
#     for the launcher's 1s poll, so the answer is cached briefly.
#   * it blocks waiting for /controller_manager when the manager is down, so the
#     call is bounded (macOS ships no coreutils `timeout`).

set -uo pipefail

MIN_ACTIVE="${1:-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TTL="${LUCY_CONTROLLERS_CACHE_TTL:-8}"
CALL_TIMEOUT="${LUCY_CONTROLLERS_TIMEOUT:-12}"
# Per Control Center instance: each one probes its own stack (launcher/instance.py).
CACHE="${TMPDIR:-/tmp}/lucy_controllers_active.$(id -u).${LUCY_TMUX_SESSION:-lucy_ws_0}.cache"

# The cache holds the active count, not a verdict, so callers asking different
# thresholds share one probe. -1 means the manager did not answer.
verdict() {
  local active="$1"
  if [[ "${active}" -lt 0 ]]; then return 1; fi
  if [[ "${active}" -ge "${MIN_ACTIVE}" ]]; then return 0; fi
  return 1
}

# Fast path: lucy_control_supervisor records "<controller_manager pid> <count>"
# once the spawners succeed, which costs nothing to read and survives a probe
# scoped differently from the stack. The pid is checked for liveness so a marker
# from a killed supervisor fails. No marker (Gazebo owns its own manager) falls
# through to the graph below.
READY_FILE="${LUCY_CONTROL_READY_FILE:-${TMPDIR:-/tmp}/lucy_control_ready.$(id -u)}"
if [[ -f "${READY_FILE}" ]]; then
  # `read` reports EOF without a trailing newline but still assigns.
  read -r ready_pid ready_active < "${READY_FILE}" 2>/dev/null
  if [[ "${ready_pid}" =~ ^[0-9]+$ ]] && [[ "${ready_active}" =~ ^[0-9]+$ ]] \
     && kill -0 "${ready_pid}" 2>/dev/null; then
    verdict "${ready_active}"
    exit $?
  fi
fi

now=$(date +%s)
if [[ -f "${CACHE}" ]]; then
  read -r stamp cached < "${CACHE}" 2>/dev/null || { stamp=0; cached=-1; }
  if [[ "${stamp}" =~ ^[0-9]+$ ]] && [[ "${cached}" =~ ^-?[0-9]+$ ]] \
     && (( now - stamp < TTL )); then
    verdict "${cached}"
    exit $?
  fi
fi

export PATH="${HOME}/.pixi/bin:${PATH}"
command -v pixi >/dev/null 2>&1 || exit 1

out="${CACHE}.out"
# Job control gives the probe its own process group so the timeout below can
# signal the whole tree. `ros2 control` runs the rclpy node as a child of
# itself, so signalling only the subshell leaves that node alive holding a DDS
# participant. One escapes per timed-out poll, and since the launcher polls
# core's readiness for as long as it is up they accumulate, loading the machine
# and adding participants that every other node then discovers and tracks.
set -m
(
  cd "${ROOT}" || exit 1
  pixi run -- bash -c 'source scripts/dds_env.sh 2>/dev/null; ros2 control list_controllers' \
    > "${out}" 2>&1
) &
probe_pid=$!
set +m

waited=0
timed_out=0
while kill -0 "${probe_pid}" 2>/dev/null && (( waited < CALL_TIMEOUT * 10 )); do
  sleep 0.1
  waited=$((waited + 1))
done
if kill -0 "${probe_pid}" 2>/dev/null; then
  timed_out=1
  kill -9 -- "-${probe_pid}" 2>/dev/null || kill -9 "${probe_pid}" 2>/dev/null
fi
# Exactly one wait: the second reap of an already-collected pid returns 127,
# which would read as a failed probe on every single call.
wait "${probe_pid}" 2>/dev/null
probe_status=$?

# grep -c prints a count and still exits 1 on zero matches, so take the count
# and normalise rather than chaining a fallback that would append a second line.
active=$(grep -cE '[[:space:]]active[[:space:]]*$' "${out}" 2>/dev/null)
[[ "${active}" =~ ^[0-9]+$ ]] || active=0
rm -f "${out}"

# A failed call says nothing about the controllers; recording its 0 would let
# the `min_active 0` stage pass while /controller_manager is still absent.
if (( timed_out )) || (( probe_status != 0 )); then
  active=-1
fi

# Stamp at completion rather than at entry. The probe above runs for as long as
# CALL_TIMEOUT, so an entry carrying the time this script *started* is already
# older than TTL by the time it is written: the slow path — the only one worth
# caching — would never produce a hit, and every caller would pay full price.
printf '%s %s\n' "$(date +%s)" "${active}" > "${CACHE}" 2>/dev/null || true
verdict "${active}"
