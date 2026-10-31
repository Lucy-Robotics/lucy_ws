#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import socket
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSBRIDGE_PORT = int(os.environ.get("PORT_ROSBRIDGE", "9090"))
PANEL_PORT = int(os.environ.get("VITE_PORT", "4004"))
MOVE_TIMEOUT_S = 20.0
IDENTITY_TIMEOUT_S = 60.0
MOVED_RAD = 0.05
SAME_RAD = 0.02
MODEL_TIMEOUT_S = 600.0
MODEL_STALL_S = 30.0
FOLLOW_TIMEOUT_S = 15.0
CLEANUP_TIMEOUT_S = 60.0
STACK_NODES = {"robot_state_publisher", "rosbridge_websocket"}
URDF_HINT_S = 25.0
WEBGL_RENDERER = """() => {
    const gl = document.createElement('canvas').getContext('webgl');
    const info = gl && gl.getExtension('WEBGL_debug_renderer_info');
    return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl ? 'unknown' : 'none';
}"""
VIEWER_ERRORS = re.compile(r"No URDF received|Could not load any meshes|WebGL is not supported|Failed to load robot model")


class CheckFailed(Exception):
    pass


def log(msg: str) -> None:
    print(f"{Path(sys.argv[0]).stem}: {msg}", flush=True)


def port_open(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


def diff(a: dict[str, float], b: dict[str, float]) -> float:
    return max((abs(a[k] - b[k]) for k in a.keys() & b.keys()), default=0.0)


class Ros:
    def __init__(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import DurabilityPolicy, QoSProfile
        from sensor_msgs.msg import JointState
        from std_msgs.msg import String

        rclpy.init(args=[])
        self.node = rclpy.create_node("lucy_ci_panel_checks")
        self.latest: dict[str, float] = {}
        self.description: str | None = None
        self.node.create_subscription(JointState, "/joint_states", self._on_joints, 10)
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.active_client: str | None = None
        self.node.create_subscription(String, "/robot_description", self._on_description, latched)
        self.node.create_subscription(String, "/lucy/active_client", self._on_active_client, latched)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.stopping = threading.Event()
        self.spinner = threading.Thread(target=self._spin, daemon=True)
        self.spinner.start()

    def _spin(self) -> None:
        while not self.stopping.is_set():
            self.executor.spin_once(timeout_sec=0.1)

    def _on_joints(self, msg) -> None:
        self.latest = {**self.latest, **dict(zip(msg.name, msg.position))}

    def _on_description(self, msg) -> None:
        self.description = msg.data

    def _on_active_client(self, msg) -> None:
        if msg.data != self.active_client:
            log(f"control lease: {msg.data or 'released'}")
        self.active_client = msg.data

    def reset(self) -> None:
        self.latest = {}
        self.description = None

    def stack_nodes(self) -> set[str]:
        return set(self.node.get_node_names()) & STACK_NODES

    def joint_states_publishers(self) -> int:
        return self.node.count_publishers("/joint_states")

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

        self.stopping.set()
        self.spinner.join(timeout=5)
        rclpy.try_shutdown()


def check_robot_identity(ros: Ros, robot: str) -> None:
    deadline = time.time() + IDENTITY_TIMEOUT_S
    while time.time() < deadline:
        urdf, joints = ros.description, set(ros.snapshot())
        if urdf and re.search(rf"[/\\]{re.escape(robot)}[/\\]", urdf) and joints:
            urdf_joints = {j.get("name") for j in ET.fromstring(urdf).iter("joint")}
            if joints <= urdf_joints:
                log(f"{robot} is the robot up: its URDF and {len(joints)} joint states")
                return
        time.sleep(1.0)
    name = re.search(r'<robot[^>]*name="([^"]*)"', ros.description or "")
    raise CheckFailed(
        f"expected {robot}, got URDF {name.group(1) if name else None} "
        f"with joint states {sorted(ros.snapshot())[:5]}"
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


def watch_model(page) -> dict:
    model: dict = {"replies": 0}

    def on_console(msg) -> None:
        m = re.search(r"\[useRobotModel\] Done .* (\d+)/(\d+) meshes", msg.text)
        if m:
            model["meshes"] = (int(m.group(1)), int(m.group(2)))
            model["done_at"] = time.time()

    def on_frame(payload) -> None:
        head = payload[:120] if isinstance(payload, str) else ""
        if '"service_response"' in head and '"/mesh/get"' in head:
            model["replies"] += 1

    page.on("console", on_console)
    page.on("websocket", lambda ws: ws.on("framereceived", on_frame))
    return model


def check_viewer(page, model: dict, opened_at: float) -> None:
    deadline = opened_at + MODEL_TIMEOUT_S
    seen, progressed_at = -1, time.time()
    while "meshes" not in model and time.time() < deadline and time.time() - progressed_at < MODEL_STALL_S:
        if model["replies"] != seen:
            seen, progressed_at = model["replies"], time.time()
        page.wait_for_timeout(1000)
    if "meshes" not in model:
        raise CheckFailed(
            f"the 3D view did not finish loading the robot: {model['replies']} mesh/get replies "
            f"in {time.time() - opened_at:.0f}s, none in the last {time.time() - progressed_at:.0f}s"
        )
    loaded, total = model["meshes"]
    if loaded != total:
        raise CheckFailed(f"the 3D view loaded only {loaded}/{total} meshes")
    page.wait_for_timeout(max(0.0, opened_at + URDF_HINT_S - time.time()) * 1000)
    shown = page.get_by_text(VIEWER_ERRORS)
    if shown.count():
        raise CheckFailed(f"the 3D view shows an error: {shown.first.inner_text()!r}")
    log(f"3D view loaded all {total} meshes in {model['done_at'] - opened_at:.0f}s "
        f"({model['replies']} mesh/get replies) and shows no error")


def check_viewer_follows(page, ros: Ros) -> None:
    canvas = max(page.locator("canvas").all(), key=lambda c: (lambda b: b["width"] * b["height"] if b else 0)(c.bounding_box()))
    before = canvas.screenshot()
    page.get_by_role("button", name=re.compile(r"reset all", re.I)).first.click()
    ros.wait_settled()
    deadline = time.time() + FOLLOW_TIMEOUT_S
    while canvas.screenshot() == before:
        if time.time() > deadline:
            raise CheckFailed(f"the 3D view did not change within {FOLLOW_TIMEOUT_S:.0f}s of RESET ALL moving the joints")
        page.wait_for_timeout(1000)
    log("3D view follows the joints")


def drive_panel(page, ros: Ros) -> None:
    from playwright.sync_api import expect

    model = watch_model(page)
    page.add_init_script("localStorage.setItem('gettingStartedCompleted', 'true')")
    opened_at = time.time()
    page.goto(f"http://127.0.0.1:{PANEL_PORT}/")
    page.locator(".ant-slider").first.wait_for(timeout=120_000)
    log(f"panel shows joint sliders (WebGL: {page.evaluate(WEBGL_RENDERER)})")

    page.get_by_role("button", name=re.compile(r"^Control Robot(: ON)?$")).first.click()
    page.locator(".ant-slider:not(.ant-slider-disabled)").first.wait_for(timeout=30_000)
    log("Control Robot is ON")

    page.get_by_role("button", name=re.compile(r"reset all", re.I)).first.click()
    start_pos = ros.wait_settled()
    log("RESET ALL settled the robot")
    drag_slider(page, 0, 0.8)
    ros.wait_for("the first slider's move", lambda s: diff(start_pos, s) > MOVED_RAD)
    pose_a = ros.wait_settled()
    log("first slider moved the robot")
    save_pose(page, "ci_a")

    drag_slider(page, 1, 0.65)
    ros.wait_for("the second slider's move", lambda s: diff(pose_a, s) > MOVED_RAD)
    pose_b = ros.wait_settled()
    log("second slider moved the robot")
    save_pose(page, "ci_b")

    modal = poses_modal(page)
    modal.locator(".ant-list-item").filter(has=page.get_by_label("Rename pose ci_a")).get_by_role(
        "button", name="LOAD"
    ).click()
    ros.wait_for("pose ci_a after LOAD", lambda s: diff(pose_a, s) < SAME_RAD)
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
    ros.wait_for("the animation heading to ci_b", lambda s: diff(pose_a, s) > halfway)
    ros.wait_for("the animation ending on ci_a", lambda s: diff(pose_a, s) < SAME_RAD)
    expect(page.get_by_role("button", name=re.compile(r"^(stop )?stop( animation)?$", re.I))).to_have_count(0)
    log("animation went to ci_b and back to ci_a")
    modal.get_by_role("button", name="CLOSE", exact=True).click()

    check_viewer(page, model, opened_at)
    check_viewer_follows(page, ros)


def exercise_panel(ros: Ros, robot: str) -> None:
    from playwright.sync_api import sync_playwright

    shot = ROOT / "log" / f"panel_e2e_{robot}.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("LUCY_E2E_BROWSER") or None)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda m: m.type == "error" and log(f"browser: {m.text}"))
        try:
            drive_panel(page, ros)
        finally:
            shot.parent.mkdir(exist_ok=True)
            page.mouse.move(0, 0)
            page.screenshot(path=str(shot), full_page=True)
            log(f"screenshot: {shot}")
            browser.close()
    log(f"panel drove {robot}")
