#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
JOINT_COMMAND_TOPIC = "/lucy/commanded_joint_states"
JOINT_STATES_TOPIC = "/joint_states"
GAZEBO_ON_ARGS = ("gazebo:=true", "gazebo:=1", "gazebo:=yes")
DDS_LOCALHOST_OFF = ("0", "false", "no", "off", "disable")
# Long enough for a working ros2_control to have spawned its broadcaster.
FALLBACK_DELAY_S = 25.0
DISCOVERY_SETTLE_S = 3.0
WINDOWS_EXEC_SUFFIXES = (".exe", ".bat", ".cmd")


def node_argv(package: str, executable: str) -> list[str]:
    """Absolute argv for a node, bypassing the ``ros2 run`` wrapper.

    That wrapper survives its own node, so stopping it leaves the node publishing.
    """
    from ament_index_python.packages import get_package_prefix

    lib_dir = Path(get_package_prefix(package)) / "lib" / package
    matches = sorted(
        (p for p in lib_dir.glob("*") if p.is_file() and p.stem == executable),
        key=lambda p: 0 if not p.suffix or p.suffix.lower() in WINDOWS_EXEC_SUFFIXES else 1,
    )
    if not matches:
        raise RuntimeError(f"{package}/{executable} not found in {lib_dir}")
    best = matches[0]
    if os.name == "nt" and best.suffix.lower() not in WINDOWS_EXEC_SUFFIXES:
        return [sys.executable, str(best)]
    return [str(best)]


def joint_states_publisher_count() -> int:
    """How many nodes already publish /joint_states (0 if it cannot be read).

    Not via `ros2 topic info`: its daemon inherits the pipe and capturing the
    output then blocks forever, even after the timeout kills the CLI.
    """
    import rclpy

    try:
        rclpy.init(args=[])
    except Exception:
        return 0
    try:
        node = rclpy.create_node("lucy_joint_state_probe")
        try:
            time.sleep(DISCOVERY_SETTLE_S)
            return node.count_publishers(JOINT_STATES_TOPIC)
        finally:
            node.destroy_node()
    except Exception:
        return 0
    finally:
        rclpy.try_shutdown()


def configure_windows_dll_search_path() -> None:
    """Ensure ROS/Pixi native DLLs are available to the current process and child processes."""
    if os.name != "nt":
        return

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if not conda_prefix:
        return

    prefix = Path(conda_prefix)

    dll_directories = [
        prefix,
        prefix / "Library" / "bin",
        prefix / "Library" / "lib",
        prefix / "Scripts",
        prefix / "bin",
    ]
    dll_directories = [directory for directory in dll_directories if directory.is_dir()]

    # Older ROS/Conda installs on Windows can leave stale DLLs earlier on PATH and
    # cause import-time ABI mismatches when loading rclpy/_rclpy_pybind11.
    current_entries = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        lower = entry.lower()
        if "miniconda" in lower or "anaconda" in lower or "opt\\ros" in lower or "opt/ros" in lower:
            continue
        current_entries.append(entry)

    path_entries = [str(directory) for directory in dll_directories] + current_entries
    os.environ["PATH"] = os.pathsep.join(path_entries)

    handles = []
    for directory in dll_directories:
        try:
            handles.append(os.add_dll_directory(str(directory)))
        except (AttributeError, OSError):
            pass

    configure_windows_dll_search_path._handles = handles


def validate_windows_ros_runtime() -> None:
    """Fail early with a guided fix when the underlying ROS Python extension is broken."""
    if os.name != "nt":
        return

    try:
        import rclpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ROS runtime is not healthy in this Pixi environment.\n"
            "This usually means a stale ROS/Conda install or missing Windows VC++ runtime is shadowing "
            "the RoboStack binaries.\n\n"
            "Fix:\n"
            "  1) Install Microsoft Visual C++ Redistributable 2015-2022 (x64)\n"
            "  2) Remove any old Anaconda/Miniconda/ROS installs from PATH\n"
            "  3) Recreate the environment: pixi install (or delete .pixi/envs/default and rerun pixi install)\n"
            "  4) Retry: pixi run core\n\n"
            f"Original import error: {exc}"
        ) from exc


def _joint_state_fallback_enabled() -> bool:
    """Whether to stand in for joint_state_broadcaster.

    controller_manager crashes on startup on win-64, so no controller spawns and
    nothing publishes /joint_states, leaving the control panel with no pose to
    draw. Set LUCY_JOINT_STATE_FALLBACK=0 once ros2_control works on Windows,
    otherwise this would publish alongside joint_state_broadcaster.
    """
    if os.name != "nt":
        return False
    value = os.environ.get("LUCY_JOINT_STATE_FALLBACK", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def _start_joint_state_fallback():
    """Stand in for joint_state_broadcaster and joint_trajectory_controller.

    joint_command_echo turns the panel's trajectory commands into JointState, and
    joint_state_publisher merges that over the URDF's full joint list, so the
    model both renders and follows the controls.
    """
    commands = [
        [sys.executable, str(ROOT / "scripts" / "joint_command_echo.py")],
        [
            *node_argv("joint_state_publisher", "joint_state_publisher"),
            "--ros-args", "-p", f"source_list:=['{JOINT_COMMAND_TOPIC}']",
        ],
    ]
    started = []
    for command in commands:
        try:
            started.append(subprocess.Popen(command, cwd=ROOT))
        except OSError as exc:
            print(f"warning: could not start {command[0]}: {exc}", file=sys.stderr)
    return started


def _start_joint_state_fallback_when_needed(started: list) -> threading.Thread:
    """Start the stand-in only once nothing else drives /joint_states.

    A second publisher makes the panel alternate between the two poses.
    """
    def wait_then_start() -> None:
        cancelled.wait(FALLBACK_DELAY_S)
        if cancelled.is_set():
            return
        existing = joint_states_publisher_count()
        if existing:
            print(
                f"{JOINT_STATES_TOPIC} already has {existing} publisher(s); not "
                "starting the stand-in, which would fight them.",
                file=sys.stderr,
            )
            return
        started.extend(_start_joint_state_fallback())

    cancelled = threading.Event()
    thread = threading.Thread(target=wait_then_start, daemon=True)
    thread.cancelled = cancelled
    thread.start()
    return thread


def _stop(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def gazebo_requested(args) -> bool:
    return any(a.strip().lower() in GAZEBO_ON_ARGS for a in args)


def refuse_gazebo_on_windows() -> None:
    """gz_ros2_control hosts a controller_manager inside the gz server, and that
    crashes on Windows, taking the server with it. Say so instead of hanging."""
    print(
        "Gazebo is not supported on Windows yet.\n"
        "gz_ros2_control runs a controller_manager inside the Gazebo server, and\n"
        "it dies there with an access violation: "
        "https://github.com/pal-robotics/pal_statistics/issues/27\n\n"
        "For the 3D view use, in two terminals:\n"
        "  pixi run core\n"
        "  pixi run control-panel",
        file=sys.stderr,
    )


def apply_dds_scope(windows: bool = os.name == "nt") -> None:
    """Scope discovery to this host, as scripts/dds_env.sh does for the shell path.

    Only that shell script set it, so Windows ran with Jazzy's SUBNET default and
    merged anyone else's Lucy into this graph. ROS_LOCALHOST_ONLY stays unset: it
    is deprecated and takes precedence, which would make rcl ignore the range.

    Windows runs Cyclone DDS pinned to loopback by the CYCLONEDDS_URI pixi.toml
    sets for every process, so the range stays SUBNET there: rmw_cyclonedds's
    LOCALHOST mode probes a port per participant index, and Windows UDP sockets
    fail on the ICMP replies from the unused ones, so nothing is discovered.
    """
    localhost = os.environ.get("LUCY_DDS_LOCALHOST", "1").strip().lower() not in DDS_LOCALHOST_OFF
    if windows and not localhost:
        os.environ.pop("CYCLONEDDS_URI", None)
    if os.environ.get("LUCY_DDS_RANGE"):
        os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = os.environ["LUCY_DDS_RANGE"]
    elif localhost and not windows:
        os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
    else:
        os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "SUBNET"

    peers = os.environ.get("LUCY_DDS_PEERS", "")
    if peers:
        # Additive to localhost, not a replacement for it. rcl splits on ';'.
        os.environ["ROS_STATIC_PEERS"] = ";".join(
            p for p in "".join(peers.split()).split(",") if p
        )


def main() -> int:
    if os.name == "nt" and gazebo_requested(sys.argv[1:]):
        refuse_gazebo_on_windows()
        return 1

    apply_dds_scope()
    configure_windows_dll_search_path()
    validate_windows_ros_runtime()

    robot = os.environ.get("LUCY_ROBOT_PACKAGE", "inmoov_urdf")

    command = [
        "ros2",
        "launch",
        "lucy_bringup",
        "lucy.launch.py",
        f"robot_package:={robot}",
        *sys.argv[1:],
    ]

    fallback: list = []
    waiter = (
        _start_joint_state_fallback_when_needed(fallback)
        if _joint_state_fallback_enabled()
        else None
    )
    try:
        return subprocess.call(command, cwd=ROOT)
    finally:
        if waiter is not None:
            waiter.cancelled.set()
            waiter.join(timeout=5)
        for proc in fallback:
            _stop(proc)


if __name__ == "__main__":
    raise SystemExit(main())
