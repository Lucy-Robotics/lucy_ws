#!/usr/bin/env bash
# Interactive Pixi shell with RoboStack + colcon overlay (for ros2 CLI debugging).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
echo "Lucy dev shell — RoboStack + install/ overlay active."
echo ""
echo "  ros2 topic list          ros2 service list"
echo "  ros2 launch lucy_bringup lucy.launch.py rviz:=true"
echo ""
echo "  Or use pixi component tasks from another terminal:"
echo "    pixi run core | rviz | sim-headless | sim-rviz | real-linux | real-mcu-bridge"
echo "    pixi run control-panel | rqt | lucy-cli"
echo ""
echo "  Robot package (default: the installed one, inmoov_urdf if several):"
echo "    LUCY_ROBOT_PACKAGE=thais_urdf pixi run sim-headless"
echo "  Another robot on the network: pixi run core -- domain_id:=3"
echo "    then ROS_DOMAIN_ID=3 for ros2 / rqt in this shell"
echo ""
exec pixi shell
