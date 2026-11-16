#!/usr/bin/env bash
# Throwaway CI diagnostic: replay the panel's /mesh/get traffic over rosbridge with no browser.
set -u
mesh_dir="src/inmoov_urdf/description/robot_description/meshes/dae"
ws_modules="$PWD/src/lucy_control_panel/node_modules"

run_variant() {
  local name="$1" rmw="$2"
  echo "::group::mesh replay: $name"
  if [ -n "$rmw" ]; then export RMW_IMPLEMENTATION="$rmw"; else unset RMW_IMPLEMENTATION; fi
  pixi run core robot_package:=inmoov_urdf > "diag_core_$name.log" 2>&1 &
  local core=$!
  for _ in $(seq 1 90); do (exec 3<>/dev/tcp/127.0.0.1/9090) 2>/dev/null && break; sleep 2; done
  sleep 25
  for conc in 2 8; do
    echo "variant=$name"
    timeout 200 pixi run node scripts/diag_mesh_replay.cjs "$ws_modules" "$PWD/$mesh_dir" "$conc" 60 2>&1 | tail -2
  done
  kill "$core" 2>/dev/null
  pkill -f "[r]os2 launch" 2>/dev/null
  sleep 8
  pkill -9 -f "[r]osbridge" 2>/dev/null
  pkill -9 -f "[c]ontrol_supervisor" 2>/dev/null
  pkill -9 -f "[c]onfig_services" 2>/dev/null
  sleep 3
  echo "::endgroup::"
}

run_variant default ""
run_variant cyclone rmw_cyclonedds_cpp
run_variant fastdds rmw_fastrtps_cpp
exit 0
