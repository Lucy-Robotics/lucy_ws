#!/usr/bin/env bash
# Throwaway CI diagnostic: replay the panel's /mesh/get traffic with no browser,
# directly on rosbridge (9090) and through the panel's vite /rosbridge proxy (4004).
set -u
mesh_dir="src/inmoov_urdf/description/robot_description/meshes/dae"
ws_modules="$PWD/src/lucy_control_panel/node_modules"

replay() {
  local label="$1" url="$2" conc="$3"
  echo "replay=$label conc=$conc"
  WS_URL="$url" pixi run node scripts/diag_mesh_replay.cjs "$ws_modules" "$PWD/$mesh_dir" "$conc" 60 2>&1 | tail -2
}

stop_all() {
  kill "$1" "$2" 2>/dev/null
  pkill -f "[r]os2 launch" 2>/dev/null
  pkill -f "[v]ite" 2>/dev/null
  sleep 8
  pkill -9 -f "[r]osbridge" 2>/dev/null
  pkill -9 -f "[c]ontrol_supervisor" 2>/dev/null
  pkill -9 -f "[c]onfig_services" 2>/dev/null
  sleep 3
}

run_variant() {
  local name="$1" rmw="$2"
  echo "::group::mesh replay: $name"
  if [ -n "$rmw" ]; then export RMW_IMPLEMENTATION="$rmw"; else unset RMW_IMPLEMENTATION; fi
  pixi run core robot_package:=inmoov_urdf > "diag_core_$name.log" 2>&1 &
  local core=$!
  pixi run control-panel > "diag_panel_$name.log" 2>&1 &
  local panel=$!
  for _ in $(seq 1 90); do (exec 3<>/dev/tcp/127.0.0.1/9090) 2>/dev/null && break; sleep 2; done
  sleep 25
  echo "variant=$name"
  replay direct ws://127.0.0.1:9090 8
  replay proxy ws://127.0.0.1:4004/rosbridge 2
  replay proxy ws://127.0.0.1:4004/rosbridge 8
  replay proxy ws://127.0.0.1:4004/rosbridge 8
  stop_all "$core" "$panel"
  echo "::endgroup::"
}

run_variant default ""
run_variant cyclone rmw_cyclonedds_cpp
exit 0
