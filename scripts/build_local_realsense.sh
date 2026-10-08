#!/usr/bin/env bash
# Build Intel librealsense and realsense-ros locally (not via Pixi/RoboStack).
#
# RoboStack does not publish ros-jazzy-realsense2-camera reliably across platforms
# (especially linux-aarch64). Use this script when you need RealSense
# hardware support.
#
# Usage:
#   ./scripts/build_local_realsense.sh              # default prefix: .local/realsense
#   LUCY_REALSENSE_PREFIX=/opt/realsense ./scripts/build_local_realsense.sh
#
# Run after a normal workspace build (install/setup.bash must exist). Does not
# replace pixi run build — it adds librealsense + realsense-ros to install/.
# install.py runs this when LUCY_BUILD_REALSENSE=1 (after colcon + panel-install).
#
# Uses a portable CPU count for cmake -j (nproc on Linux, sysctl on macOS).

set -euo pipefail

parallel_jobs() {
  nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PREFIX="${LUCY_REALSENSE_PREFIX:-${WORKSPACE_ROOT}/.local/realsense}"
LIBRS_TAG="${LUCY_LIBRS_TAG:-v2.56.2}"
REALSENSE_ROS_BRANCH="${LUCY_REALSENSE_ROS_BRANCH:-ros2-master}"
BUILD_DIR="${WORKSPACE_ROOT}/.local/build/realsense"
SRC_DIR="${WORKSPACE_ROOT}/.local/src"

mkdir -p "$BUILD_DIR" "$SRC_DIR" "$PREFIX"

build_librealsense() {
  local librs_dir="${SRC_DIR}/librealsense"
  if [ ! -d "$librs_dir/.git" ]; then
    echo "Cloning librealsense (${LIBRS_TAG}) ..."
    git clone --depth 1 --branch "$LIBRS_TAG" https://github.com/IntelRealSense/librealsense.git "$librs_dir"
  else
    echo "Using existing librealsense clone at $librs_dir"
  fi

  cmake -S "$librs_dir" -B "${BUILD_DIR}/librealsense" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_GRAPHICAL_EXAMPLES=OFF \
    -DBUILD_WITH_OPENMP=OFF

  cmake --build "${BUILD_DIR}/librealsense" -j"$(parallel_jobs)"
  cmake --install "${BUILD_DIR}/librealsense"
}

build_realsense_ros() {
  local rs_ros_dir="${SRC_DIR}/realsense-ros"
  if [ ! -d "$rs_ros_dir/.git" ]; then
    echo "Cloning realsense-ros (${REALSENSE_ROS_BRANCH}) ..."
    git clone --depth 1 --branch "$REALSENSE_ROS_BRANCH" https://github.com/IntelRealSense/realsense-ros.git "$rs_ros_dir"
  else
    echo "Using existing realsense-ros clone at $rs_ros_dir"
  fi

  export CMAKE_PREFIX_PATH="${PREFIX}:${CMAKE_PREFIX_PATH:-}"
  export LD_LIBRARY_PATH="${PREFIX}/lib:${LD_LIBRARY_PATH:-}"

  # Build into workspace overlay (requires ROS env from pixi shell / install/setup.bash).
  if [ -f "${WORKSPACE_ROOT}/install/setup.bash" ]; then
  # shellcheck disable=SC1091
    source "${WORKSPACE_ROOT}/install/setup.bash"
  elif [ -n "${ROS_DISTRO:-}" ]; then
    # shellcheck disable=SC1091
    source "/opt/ros/${ROS_DISTRO}/setup.bash"
  else
    echo "ROS environment not found. Run from pixi shell or after colcon build." >&2
    exit 1
  fi

  colcon build --symlink-install \
    --paths "$rs_ros_dir/realsense2_camera_msgs" "$rs_ros_dir/realsense2_camera" \
    --cmake-args -DCMAKE_PREFIX_PATH="$PREFIX"
}

echo "Local RealSense build — install prefix: $PREFIX"
build_librealsense
build_realsense_ros
echo "Done. Prefix: $PREFIX"
