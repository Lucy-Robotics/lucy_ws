#!/usr/bin/env bash
# Run lucy_bringup inside Pixi with host GL env (scripts/nix_gl_env.sh).
#
# Usage:
#   pixi run core
#   pixi run sim-headless
#   LUCY_ROBOT_PACKAGE=thais_urdf pixi run sim-rviz
#
# Extra ros2 launch args are forwarded:
#   bash scripts/pixi_lucy_launch.sh mode:=sim headless:=true
#   pixi run core -- domain_id:=3
#
# robot_package:= is only passed when LUCY_ROBOT_PACKAGE is set; otherwise
# lucy.launch.py picks the installed robot package itself.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/nix_gl_env.sh
source "${ROOT}/scripts/nix_gl_env.sh"
# shellcheck source=scripts/dds_env.sh
source "${ROOT}/scripts/dds_env.sh"
ROBOT_ARGS=()
if [[ -n "${LUCY_ROBOT_PACKAGE:-}" ]]; then
  ROBOT_ARGS=("robot_package:=${LUCY_ROBOT_PACKAGE}")
fi
cd "${ROOT}"
# ${a[@]+...}: an empty array trips set -u on macOS bash 3.2.
exec ros2 launch lucy_bringup lucy.launch.py ${ROBOT_ARGS[@]+"${ROBOT_ARGS[@]}"} "$@"
