#!/usr/bin/env bash
# Exit 0 when every host SHM consumer listed by lucy.launch.py is running.
# Expectation file lines (written by bringup):
#   linux <node_name>
#   mcu-bridge <node_name> <usb_serial>
set -euo pipefail

expected_file="${LUCY_REAL_HARDWARE_EXPECTED:-/tmp/.lucy_real_hardware_expected}"
[[ -f "$expected_file" ]] || exit 1

found_line=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "${line// }" || "$line" == \#* ]] && continue
  found_line=1
  # shellcheck disable=SC2086
  set -- $line
  kind="${1:-}"
  case "$kind" in
    linux)
      node="${2:-}"
      [[ -n "$node" ]] || exit 1
      pgrep -f "[l]ucy-embedded-firmware-linux ${node}" >/dev/null 2>&1 || exit 1
      ;;
    mcu-bridge)
      node="${2:-}"
      serial="${3:-}"
      [[ -n "$node" && -n "$serial" ]] || exit 1
      pgrep -f "[l]ucy-embedded-firmware-mcu-bridge ${node} ${serial}" >/dev/null 2>&1 || exit 1
      ;;
    *)
      exit 1
      ;;
  esac
done <"$expected_file"

[[ "$found_line" -eq 1 ]]
