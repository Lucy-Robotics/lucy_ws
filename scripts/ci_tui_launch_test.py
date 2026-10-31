#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

from ci_panel_checks import (
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

OUTER_SOCKET = "lucy_ci_outer"
SESSION = os.environ.get("LUCY_TMUX_SESSION", "lucy_ws")
UP_TIMEOUT_S = float(os.environ.get("LUCY_CI_BRINGUP_TIMEOUT", "300"))
FEEDBACK_LAG_S = 30.0
STEADY_S = 20.0
MAX_LAUNCHER_CPU_S = 5.0
CORE_PATTERN = "bin/[r]os2 launch lucy_bringup"
STACK_PATTERNS = (CORE_PATTERN, "[r]osbridge_websocket", "[r]obot_state_publisher", "[r]os2_control_node", "[v]ite/bin/vite")


def tmux(*args: str, outer: bool = False) -> str:
    cmd = ["tmux", *(["-L", OUTER_SOCKET] if outer else []), *args]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def pids(pattern: str) -> set[int]:
    out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout
    return {int(p) for p in out.split()}


def cpu_seconds(pid: int) -> float:
    out = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    days, _, hms = out.rpartition("-")
    secs = 0.0
    for part in hms.split(":"):
        secs = secs * 60 + float(part)
    return secs + (int(days) * 86400 if days else 0)


def panel_serves() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PANEL_PORT}/", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def screen() -> str:
    return tmux("capture-pane", "-p", "-t", f"{SESSION}:Lucy")


def status(name: str) -> str | None:
    m = re.search(rf"\] {re.escape(name)} \[([A-Z]+)\]", screen())
    return m.group(1) if m else None


def robot_label(robot: str) -> str:
    packages = json.loads((ROOT / "config" / "launcher_config.json").read_text())["packages"]
    return next(p["name"] for p in packages if p.get("command") == f"robot_package:={robot}")


def wait_for(what: str, ok, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if ok():
            return
        time.sleep(2.0)
    raise CheckFailed(f"timed out waiting for {what}")


def core_up(ros: Ros) -> bool:
    return bool(pids(CORE_PATTERN)) and port_open(ROSBRIDGE_PORT) and ros.joint_states_publishers() > 0


def select_robot(robot: str) -> bool:
    label = re.escape(robot_label(robot))
    for _ in range(40):
        lines = screen().splitlines()
        row = next((i for i, line in enumerate(lines) if re.search(rf"\] {label} \[", line)), None)
        cursor = next((i for i, line in enumerate(lines) if re.match(r"\s*> ", line)), None)
        if row is None or cursor is None:
            raise CheckFailed(f"no {robot_label(robot)} row or cursor in the TUI:\n{screen()}")
        if row == cursor:
            if re.search(rf"\[x\] {label} \[", lines[row]):
                return False
            tmux("send-keys", "-t", f"{SESSION}:Lucy", "Space")
            time.sleep(0.5)
            tmux("send-keys", "-t", f"{SESSION}:Lucy", "Enter")
            log(f"TUI: selected {robot_label(robot)} and applied")
            return True
        tmux("send-keys", "-t", f"{SESSION}:Lucy", "Down" if row > cursor else "Up")
        time.sleep(0.3)
    raise CheckFailed(f"could not move the TUI cursor to {robot_label(robot)}")


def check_feedback_matches(ros: Ros) -> None:
    up_since: float | None = None
    deadline = time.time() + UP_TIMEOUT_S
    while time.time() < deadline:
        core, panel = status("Core"), status("Control Panel")
        is_core_up, is_panel_up = core_up(ros), panel_serves()
        if core == "RUNNING" and not is_core_up:
            raise CheckFailed("TUI says Core RUNNING but rosbridge or /joint_states is down")
        if panel == "RUNNING" and not is_panel_up:
            raise CheckFailed("TUI says Control Panel RUNNING but the panel does not answer")
        if core == "RUNNING" and panel == "RUNNING":
            log("Core and Control Panel RUNNING, and they are")
            return
        if is_core_up and is_panel_up:
            up_since = up_since or time.time()
            if time.time() - up_since > FEEDBACK_LAG_S:
                raise CheckFailed(f"stack up for {FEEDBACK_LAG_S:.0f}s but TUI shows Core={core} Panel={panel}")
        time.sleep(2.0)
    raise CheckFailed(f"not up within {UP_TIMEOUT_S:.0f}s; TUI shows:\n{screen()}")


def run_robot(ros: Ros, robot: str) -> None:
    old_core = pids(CORE_PATTERN)
    if select_robot(robot) and old_core:
        wait_for("the previous core to stop after the robot change",
                 lambda: not (pids(CORE_PATTERN) & old_core), 60.0)
        log("previous core stopped")
    ros.reset()
    check_feedback_matches(ros)
    check_robot_identity(ros, robot)
    exercise_panel(ros, robot)


def check_steady() -> None:
    launcher = min(pids("bin/python[0-9.]* -m [l]auncher"))
    core = pids(CORE_PATTERN)
    cpu0 = cpu_seconds(launcher)
    end = time.time() + STEADY_S
    while time.time() < end:
        if (status("Core"), status("Control Panel")) != ("RUNNING", "RUNNING"):
            raise CheckFailed(f"status flapped while steady:\n{screen()}")
        if pids(CORE_PATTERN) != core:
            raise CheckFailed(f"core restarted while steady ({core} -> {pids(CORE_PATTERN)})")
        time.sleep(2.0)
    cpu = cpu_seconds(launcher) - cpu0
    if cpu > MAX_LAUNCHER_CPU_S:
        raise CheckFailed(f"launcher used {cpu:.1f}s CPU in {STEADY_S:.0f}s: busy loop")
    log(f"steady for {STEADY_S:.0f}s, launcher used {cpu:.1f}s CPU")


def check_crash_reported() -> None:
    for pid in pids("[r]osbridge_websocket"):
        os.kill(pid, signal.SIGKILL)
    wait_for("the TUI to stop calling Core RUNNING after rosbridge died",
             lambda: status("Core") not in ("RUNNING", None), FEEDBACK_LAG_S)
    log(f"rosbridge killed, TUI shows Core {status('Core')}")


def check_exit_cleans_up() -> None:
    tmux("send-keys", "-t", f"{SESSION}:Lucy", "q")
    time.sleep(1.0)
    tmux("send-keys", "-t", f"{SESSION}:Lucy", "y")
    try:
        wait_for("every stack process to stop after Exit",
                 lambda: not any(pids(p) for p in STACK_PATTERNS), 60.0)
    except CheckFailed:
        left = [p for p in STACK_PATTERNS if pids(p)]
        raise CheckFailed(f"still running 60s after Exit: {left}")
    log("Exit stopped every stack process")


def main() -> int:
    robots = sys.argv[1:] or ["inmoov_urdf", "so_arm101_urdf"]
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    tmux("kill-server", outer=True)
    subprocess.run(
        ["tmux", "-L", OUTER_SOCKET, "new-session", "-d", "-x", "200", "-y", "50",
         f"unset TMUX; cd '{ROOT}' && python3 Lucy.py"],
        check=True, env=env,
    )
    wait_for("the Lucy.py menu", lambda: "Launch" in tmux("capture-pane", "-p", outer=True), 60.0)
    tmux("send-keys", "Enter", outer=True)
    log("Lucy.py: Launch")

    ros = Ros()
    try:
        wait_for("the launcher window", lambda: status("Core") is not None, 120.0)
        for robot in robots:
            run_robot(ros, robot)
        check_steady()
        check_crash_reported()
        check_exit_cleans_up()
    except Exception as exc:
        log(f"FAIL: {exc}")
        print(f"[launcher]\n{screen()}\n[Lucy.py]\n{tmux('capture-pane', '-p', outer=True)}", flush=True)
        return 1
    finally:
        ros.close()
        tmux("kill-session", "-t", SESSION)
        tmux("kill-server", outer=True)
    log(f"PASS ({', '.join(robots)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
