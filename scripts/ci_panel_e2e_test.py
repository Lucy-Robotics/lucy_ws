#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL_DIR = ROOT / "src" / "lucy_control_panel"
ROSBRIDGE_PORT = int(os.environ.get("PORT_ROSBRIDGE", "9090"))
PANEL_PORT = int(os.environ.get("VITE_PORT", "4004"))
BRINGUP_TIMEOUT_S = float(os.environ.get("LUCY_CI_BRINGUP_TIMEOUT", "300"))
MOVE_TIMEOUT_S = 20.0
MOVED_RAD = 0.05
SAME_RAD = 0.02


class CheckFailed(Exception):
    pass


def log(msg: str) -> None:
    print(f"ci_panel_e2e: {msg}", flush=True)


def start(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    exe = shutil.which(cmd[0])
    if not exe:
        raise CheckFailed(f"{cmd[0]} not found on PATH")
    kwargs = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    return subprocess.Popen([exe, *cmd[1:]], cwd=cwd, env=env, **kwargs)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        return
    os.killpg(proc.pid, signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)


def port_open(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


class JointStates:
    def __init__(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from sensor_msgs.msg import JointState

        rclpy.init(args=[])
        self.node = rclpy.create_node("lucy_ci_panel_e2e")
        self.latest: dict[str, float] = {}
        self.node.create_subscription(JointState, "/joint_states", self._on_msg, 10)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        threading.Thread(target=self.executor.spin, daemon=True).start()

    def _on_msg(self, msg) -> None:
        self.latest = {**self.latest, **dict(zip(msg.name, msg.position))}

    def snapshot(self) -> dict[str, float]:
        return dict(self.latest)

    def wait_for(self, what: str, ok, timeout_s: float = MOVE_TIMEOUT_S) -> dict[str, float]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            snap = self.snapshot()
            if snap and ok(snap):
                return snap
            time.sleep(0.2)
        raise CheckFailed(f"/joint_states never showed {what} (last: {self.snapshot()})")

    def wait_settled(self) -> dict[str, float]:
        prev = self.snapshot()
        deadline = time.time() + MOVE_TIMEOUT_S
        while time.time() < deadline:
            time.sleep(1.0)
            snap = self.snapshot()
            if prev and diff(prev, snap) < 1e-4:
                return snap
            prev = snap
        raise CheckFailed(f"/joint_states never settled (last: {prev})")

    def close(self) -> None:
        import rclpy

        self.executor.shutdown()
        self.node.destroy_node()
        rclpy.try_shutdown()


def diff(a: dict[str, float], b: dict[str, float]) -> float:
    return max((abs(a[k] - b[k]) for k in a.keys() & b.keys()), default=0.0)


def wait_for_stack(states: JointStates, procs: list[subprocess.Popen]) -> None:
    deadline = time.time() + BRINGUP_TIMEOUT_S
    while time.time() < deadline:
        dead = [p.args[1] for p in procs if p.poll() is not None]
        if dead:
            raise CheckFailed(f"exited before the stack came up: {dead}")
        if port_open(ROSBRIDGE_PORT) and port_open(PANEL_PORT) and states.snapshot():
            log("rosbridge, panel and /joint_states are up")
            return
        time.sleep(2.0)
    raise CheckFailed(
        f"stack not up within {BRINGUP_TIMEOUT_S:.0f}s (rosbridge={port_open(ROSBRIDGE_PORT)}, "
        f"panel={port_open(PANEL_PORT)}, joint_states={bool(states.snapshot())})"
    )


def drag_slider(page, index: int, fraction: float) -> None:
    rail = page.locator(".ant-slider:not(.ant-slider-disabled)").nth(index)
    rail.scroll_into_view_if_needed()
    box = rail.bounding_box()
    page.mouse.click(box["x"] + box["width"] * fraction, box["y"] + box["height"] / 2)


def poses_modal(page):
    page.get_by_role("button", name=re.compile("manage poses", re.I)).first.click()
    page.get_by_placeholder("Pose name").wait_for()
    return page


def save_pose(page, name: str) -> None:
    modal = poses_modal(page)
    modal.get_by_placeholder("Pose name").fill(name)
    modal.get_by_role("button", name="SAVE POSE").click()
    modal.get_by_label(f"Rename pose {name}").wait_for()
    modal.get_by_role("button", name="CLOSE", exact=True).click()
    log(f"saved pose {name}")


def run(page, states: JointStates) -> None:
    from playwright.sync_api import expect

    page.add_init_script("localStorage.setItem('gettingStartedCompleted', 'true')")
    page.goto(f"http://127.0.0.1:{PANEL_PORT}/")
    page.locator(".ant-slider").first.wait_for(timeout=120_000)
    log("panel shows joint sliders")

    page.get_by_role("button", name=re.compile(r"^Control Robot(: ON)?$")).first.click()
    page.locator(".ant-slider:not(.ant-slider-disabled)").first.wait_for(timeout=30_000)
    log("Control Robot is ON")
    expect(page.get_by_text("No URDF received")).to_have_count(0, timeout=60_000)

    start_pos = states.wait_settled()
    drag_slider(page, 0, 0.8)
    states.wait_for("the first slider's move", lambda s: diff(start_pos, s) > MOVED_RAD)
    pose_a = states.wait_settled()
    log("first slider moved the robot")
    save_pose(page, "ci_a")

    drag_slider(page, 1, 0.65)
    states.wait_for("the second slider's move", lambda s: diff(pose_a, s) > MOVED_RAD)
    pose_b = states.wait_settled()
    log("second slider moved the robot")
    save_pose(page, "ci_b")

    modal = poses_modal(page)
    modal.locator(".ant-list-item").filter(has=page.get_by_label("Rename pose ci_a")).get_by_role(
        "button", name="LOAD"
    ).click()
    states.wait_for("pose ci_a after LOAD", lambda s: diff(pose_a, s) < SAME_RAD)
    log("loading ci_a restored its joints")

    modal.get_by_placeholder("Animation name").fill("ci_anim")
    modal.get_by_role("button", name=re.compile(r"(^|\s)ci_b$")).click()
    modal.get_by_role("button", name=re.compile(r"(^|\s)ci_a$")).click()
    modal.get_by_role("button", name="Loop: OFF").click()
    modal.get_by_role("button", name="CREATE ANIMATION").click()
    modal.locator(".ant-select").filter(has_text="Select animation to edit").click()
    page.locator(".ant-select-item-option").filter(has_text="ci_anim").click()
    modal.get_by_role("button", name="PLAY").click()
    halfway = diff(pose_a, pose_b) / 2
    states.wait_for("the animation heading to ci_b", lambda s: diff(pose_a, s) > halfway)
    states.wait_for("the animation ending on ci_a", lambda s: diff(pose_a, s) < SAME_RAD)
    expect(page.get_by_role("button", name=re.compile(r"^(stop )?stop( animation)?$", re.I))).to_have_count(0)
    log("animation went to ci_b and back to ci_a")


def main() -> int:
    robot = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LUCY_ROBOT_PACKAGE", "inmoov_urdf")
    env = {**os.environ, "LUCY_ROBOT_PACKAGE": robot}
    core_cmd = ["python", "scripts/pixi_lucy_launch.py"] if os.name == "nt" else ["bash", "scripts/pixi_lucy_launch.sh"]
    procs = [start(core_cmd, ROOT, env), start(["yarn", "dev"], PANEL_DIR, env)]
    log(f"started core ({robot}, mock hardware) and the panel")

    from playwright.sync_api import sync_playwright

    states = JointStates()
    shot = ROOT / "log" / f"panel_e2e_{robot}.png"
    try:
        wait_for_stack(states, procs)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get("LUCY_E2E_BROWSER") or None)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("console", lambda m: m.type == "error" and log(f"browser: {m.text}"))
            try:
                run(page, states)
            except Exception:
                shot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
                log(f"screenshot: {shot}")
                raise
            finally:
                browser.close()
    except CheckFailed as exc:
        log(f"FAIL: {exc}")
        return 1
    finally:
        states.close()
        for proc in procs:
            stop(proc)
    log(f"PASS ({robot})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
