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
MOVED_RAD = 0.05
SAME_RAD = 0.02
IDENTITY_TIMEOUT_S = 60.0
CLEANUP_TIMEOUT_S = 60.0
STACK_NODES = {"robot_state_publisher", "rosbridge_websocket"}


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
        self.stopping.set()
        self.spinner.join(timeout=5)


def exit_skipping_ros_teardown(code: int) -> None:
    """Exit with the verdict; rcl's native teardown can hang at interpreter exit."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


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


def path_outside(root, path: str) -> str:
    prefix = str(root).lower()
    return os.pathsep.join(entry for entry in path.split(os.pathsep) if not entry.lower().startswith(prefix))
