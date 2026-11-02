#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request

from ci_stack import PANEL_PORT, ROOT, CheckFailed, log

OUTER_SOCKET = "lucy_ci_outer"
SESSION = os.environ.get("LUCY_TMUX_SESSION", "lucy_ws")


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
