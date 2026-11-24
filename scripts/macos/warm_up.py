from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROBOT_PACKAGES = ("so_arm101_urdf", "inmoov_urdf", "inmoov_i2_urdf")
WARM_UP_DOMAIN_ID = "101"
READY_TIMEOUT_S = 600
STOP_TIMEOUT_S = 30


def installed_robot(project_root: Path) -> str | None:
    return next((p for p in ROBOT_PACKAGES if (project_root / "install" / p).is_dir()), None)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def mock_launch_command(robot: str) -> list[str]:
    return ["ros2", "launch", "lucy_bringup", "lucy.launch.py", f"robot_package:={robot}", "mode:=mock"]


def warm_up_environment(ready_file: Path, port: int) -> dict[str, str]:
    return {
        **os.environ,
        "ROS_DOMAIN_ID": WARM_UP_DOMAIN_ID,
        "PORT_ROSBRIDGE": str(port),
        "LUCY_CONTROL_READY_FILE": str(ready_file),
        "LUCY_TMUX_SESSION": "lucy_warm_up",
    }


def wait_until_ready(process, ready_file: Path, timeout_s: float, clock=time.monotonic, nap=time.sleep) -> bool:
    deadline = clock() + timeout_s
    while clock() < deadline:
        if ready_file.is_file():
            return True
        if process.poll() is not None:
            return False
        nap(1.0)
    return False


def stop(process) -> None:
    for sig in (signal.SIGINT, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=STOP_TIMEOUT_S)
            return
        except subprocess.TimeoutExpired:
            continue


def main(project_root: Path) -> int:
    robot = installed_robot(project_root)
    if robot is None:
        print("Warm-up skipped: no robot package installed.", flush=True)
        return 0
    print(f"Starting Lucy once in mock mode ({robot}) so macOS runs its first-load security "
          "checks now, not at your first launch ...", flush=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        ready_file = Path(tmp) / "control_ready"
        process = subprocess.Popen(
            mock_launch_command(robot), cwd=str(project_root),
            env=warm_up_environment(ready_file, free_port()),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        try:
            ready = wait_until_ready(process, ready_file, READY_TIMEOUT_S)
        finally:
            stop(process)
    outcome = "done" if ready else "stopped before the robot was ready"
    print(f"Warm-up {outcome} in {time.monotonic() - started:.0f}s.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parents[2]))
