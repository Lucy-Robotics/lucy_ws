#!/usr/bin/env python3

from __future__ import annotations

import faulthandler
import os
import shutil
import signal
import subprocess
import sys
import time

from ci_panel_checks import (
    CLEANUP_TIMEOUT_S,
    PANEL_PORT,
    ROOT,
    ROSBRIDGE_PORT,
    CheckFailed,
    Ros,
    check_robot_identity,
    exercise_panel,
    log,
    port_open,
)

BRINGUP_TIMEOUT_S = float(os.environ.get("LUCY_CI_BRINGUP_TIMEOUT", "300"))
DISCOVERY_S = 3.0
PREVIOUS_STACK_TIMEOUT_S = 30.0


def start(pixi_args: str) -> subprocess.Popen:
    if os.name == "nt":
        return subprocess.Popen(
            f'cmd.exe /d /s /c "pixi run {pixi_args}"', cwd=ROOT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen([shutil.which("pixi"), "run", *pixi_args.split()], cwd=ROOT, start_new_session=True)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        return
    os.killpg(proc.pid, signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)


def wait_for_stack(ros: Ros, procs: dict[str, subprocess.Popen]) -> None:
    deadline = time.time() + BRINGUP_TIMEOUT_S
    while time.time() < deadline:
        dead = [name for name, p in procs.items() if p.poll() is not None]
        if dead:
            raise CheckFailed(f"exited before the stack came up: {dead}")
        if port_open(ROSBRIDGE_PORT) and port_open(PANEL_PORT) and ros.snapshot():
            log("rosbridge, panel and /joint_states are up")
            return
        time.sleep(2.0)
    raise CheckFailed(
        f"stack not up within {BRINGUP_TIMEOUT_S:.0f}s (rosbridge={port_open(ROSBRIDGE_PORT)}, "
        f"panel={port_open(PANEL_PORT)}, joint_states={bool(ros.snapshot())})"
    )


def wait_for_previous_stack(ros: Ros) -> None:
    time.sleep(DISCOVERY_S)
    deadline = time.time() + PREVIOUS_STACK_TIMEOUT_S
    while (left := ros.stack_nodes()) and time.time() < deadline:
        time.sleep(1.0)
    if left:
        raise CheckFailed(f"a previous stack is still running: {sorted(left)}")


def main() -> int:
    robot = sys.argv[1] if len(sys.argv) > 1 else "inmoov_urdf"
    ros = Ros()
    procs: dict[str, subprocess.Popen] = {}
    try:
        wait_for_previous_stack(ros)
        procs = {"core": start(f"core robot_package:={robot}"), "control-panel": start("control-panel")}
        log(f"started pixi run core robot_package:={robot} and pixi run control-panel")
        wait_for_stack(ros, procs)
        check_robot_identity(ros, robot)
        exercise_panel(ros, robot)
    except Exception as exc:
        log(f"FAIL: {exc}")
        return 1
    finally:
        faulthandler.dump_traceback_later(CLEANUP_TIMEOUT_S, exit=True)
        ros.close()
        for proc in procs.values():
            stop(proc)
    log(f"PASS ({robot})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
