#!/usr/bin/env python3
"""CI: bring core up and assert the ROS graph is usable.

ci_tmux_launcher_smoke.sh checks that the processes started. This checks that
the graph they formed is one the control panel and RViz can actually use.

Run under Pixi, from a built workspace:  pixi run core-bringup-test
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
TMUX_SESSION = os.environ.get("LUCY_TMUX_SESSION", "lucy_ws")


def _host_tmux(*args: str) -> list[str]:
    """argv for host tmux without Pixi's LD_LIBRARY_PATH (libtinfo ABI clash)."""
    return ["env", "-u", "LD_LIBRARY_PATH", "-u", "DYLD_LIBRARY_PATH", "tmux", *args]


BRINGUP_TIMEOUT_S = float(os.environ.get("LUCY_CI_BRINGUP_TIMEOUT", "300"))
ROSBRIDGE_PORT = int(os.environ.get("PORT_ROSBRIDGE", "9090"))
GRAPH_SETTLE_S = 20.0
CONTROLLER_TIMEOUT_S = 180.0

CORE_CMD = (
    "ros2 launch lucy_bringup lucy.launch.py "
    "robot_package:=inmoov_urdf gazebo:=false"
)


class CheckFailed(Exception):
    pass


def log(msg: str) -> None:
    print(f"ci_core_bringup: {msg}", flush=True)



def start_core() -> None:
    """Launch core through the launcher's own tmux+Pixi wrapper, so the test
    covers the path production uses."""
    sys.path.insert(0, str(ROOT))
    from launcher import _tmux_new_pixi_window, load_workspace_env, run_shell_command

    load_workspace_env()
    subprocess.run(_host_tmux("start-server"), check=False)
    subprocess.run(_host_tmux("kill-session", "-t", TMUX_SESSION), check=False,
                   capture_output=True)
    subprocess.run(
        _host_tmux("new-session", "-d", "-s", TMUX_SESSION, "-n", "Lucy", "sleep 900"),
        check=True,
    )
    run_shell_command(_tmux_new_pixi_window("core", CORE_CMD, remain_on_exit=True))
    log(f"core launched in tmux session {TMUX_SESSION}")


def stop_core() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from launcher import LauncherState, load_config, load_workspace_env, stop_all_packages

        load_workspace_env()
        stop_all_packages(LauncherState(load_config()))
    except Exception as exc:  # teardown must never mask the real failure
        log(f"warning: launcher teardown raised {exc!r}")
    subprocess.run(_host_tmux("kill-session", "-t", TMUX_SESSION), check=False,
                   capture_output=True)


def dump_diagnostics() -> None:
    """Capture the session before teardown removes it."""
    log("--- diagnostics ---")
    for label, cmd in (
        ("tmux windows", _host_tmux("list-windows", "-t", TMUX_SESSION)),
        ("core pane", _host_tmux(
            "capture-pane", "-p", "-t", f"{TMUX_SESSION}:core", "-S", "-80"
        )),
    ):
        out = subprocess.run(cmd, capture_output=True, text=True)
        print(f"[{label}]\n{out.stdout or out.stderr}", flush=True)


def port_open(port: int) -> bool:
    import socket

    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


def wait_for_bringup(node) -> None:
    deadline = time.time() + BRINGUP_TIMEOUT_S
    saw_port = False
    while time.time() < deadline:
        if not saw_port and port_open(ROSBRIDGE_PORT):
            saw_port = True
            log(f"rosbridge listening on {ROSBRIDGE_PORT}")
        if saw_port and node.count_publishers("/robot_description") > 0:
            log("/robot_description has a publisher")
            return
        time.sleep(2.0)
    raise CheckFailed(
        f"core did not come up within {BRINGUP_TIMEOUT_S:.0f}s "
        f"(rosbridge port open={saw_port})"
    )



def check_single_robot_description_publisher(node) -> None:
    """More than one distinct node means another stack joined this graph.

    FastDDS (rmw_fastrtps_cpp) sometimes lists the same endpoint twice in
    ``get_publishers_info_by_topic``, so count unique (namespace, name) pairs
    rather than raw info rows.
    """
    infos = node.get_publishers_info_by_topic("/robot_description")
    unique = {(i.node_namespace, i.node_name) for i in infos}
    if len(unique) != 1:
        who = ", ".join(
            f"{ns.rstrip('/')}/{name}" for ns, name in sorted(unique)
        ) or "none"
        raise CheckFailed(
            f"expected exactly 1 publisher of /robot_description, "
            f"found {len(unique)}: {who}"
        )
    log("exactly one publisher of /robot_description")


def check_robot_description_is_latched(node) -> None:
    """A volatile publisher leaves every late subscriber with no model."""
    from rclpy.qos import DurabilityPolicy

    info = node.get_publishers_info_by_topic("/robot_description")[0]
    if info.qos_profile.durability != DurabilityPolicy.TRANSIENT_LOCAL:
        raise CheckFailed(
            "/robot_description is not transient_local, so a subscriber that "
            f"connects after it is published receives nothing (got {info.qos_profile.durability})"
        )
    log("/robot_description is transient_local")


def receive_urdf(node, timeout_s: float = 30.0) -> str:
    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String

    got: list[str] = []
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
    sub = node.create_subscription(String, "/robot_description",
                                   lambda m: got.append(m.data), qos)
    try:
        deadline = time.time() + timeout_s
        while not got and time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        node.destroy_subscription(sub)
    if not got:
        raise CheckFailed(f"no URDF on /robot_description within {timeout_s:.0f}s")
    log(f"received URDF ({len(got[0])} bytes)")
    return got[0]


def check_meshes_resolve_locally(urdf: str) -> None:
    """A URDF from another host still parses; its mesh paths just point at a
    filesystem that is not this one."""
    root = ET.fromstring(urdf)
    refs = [m.get("filename", "") for m in root.iter("mesh")]
    if not refs:
        raise CheckFailed("URDF declares no meshes at all")

    workspace = ROOT.resolve()
    missing: list[str] = []
    outside: list[str] = []
    for ref in sorted(set(refs)):
        if ref.startswith("package://"):
            continue  # resolved by the consumer's package lookup, not a path
        path = Path(unquote(urlparse(ref).path)) if ref.startswith("file://") else Path(ref)
        if not path.is_absolute() or not path.exists():
            missing.append(ref)
            continue
        if workspace not in path.resolve().parents:
            outside.append(ref)

    if missing:
        raise CheckFailed(
            f"{len(missing)} mesh reference(s) do not exist on this host, e.g. "
            f"{missing[0]} -- the URDF was almost certainly generated elsewhere"
        )
    if outside:
        raise CheckFailed(
            f"{len(outside)} mesh reference(s) point outside {workspace}, e.g. {outside[0]}"
        )
    log(f"all {len(set(refs))} mesh references resolve inside the workspace")


def check_controllers_active() -> None:
    """Wait until every loaded controller is active.

    Polled, not sampled: lucy_control_supervisor spawns controllers one at a
    time, so a single sample mid-startup returns a different set run to run.
    """
    from controller_manager_msgs.srv import ListControllers
    import rclpy
    from rclpy.node import Node

    probe = Node("ci_controller_probe")
    try:
        client = probe.create_client(ListControllers, "/controller_manager/list_controllers")
        if not client.wait_for_service(timeout_sec=CONTROLLER_TIMEOUT_S):
            raise CheckFailed("/controller_manager/list_controllers never became available")

        deadline = time.time() + CONTROLLER_TIMEOUT_S
        states: dict[str, str] = {}
        while time.time() < deadline:
            future = client.call_async(ListControllers.Request())
            rclpy.spin_until_future_complete(probe, future, timeout_sec=15.0)
            if future.done() and future.result() is not None:
                states = {c.name: c.state for c in future.result().controller}
                if states and all(st == "active" for st in states.values()):
                    log(f"{len(states)} controller(s) active: {', '.join(sorted(states))}")
                    return
            time.sleep(2.0)

        if not states:
            raise CheckFailed(
                f"controller_manager loaded no controllers within {CONTROLLER_TIMEOUT_S:.0f}s"
            )
        stuck = {n: st for n, st in states.items() if st != "active"}
        raise CheckFailed(
            f"controller(s) never reached active within {CONTROLLER_TIMEOUT_S:.0f}s: {stuck}"
        )
    finally:
        probe.destroy_node()


def check_urdf_reaches_a_websocket_client() -> None:
    """The control panel's own path: rosbridge, not DDS."""
    import asyncio

    from tornado.websocket import websocket_connect

    async def fetch() -> str | None:
        conn = await websocket_connect(f"ws://127.0.0.1:{ROSBRIDGE_PORT}")
        await conn.write_message(json.dumps({
            "op": "subscribe",
            "topic": "/robot_description",
            "type": "std_msgs/msg/String",
        }))
        try:
            while True:
                raw = await asyncio.wait_for(conn.read_message(), timeout=30.0)
                if raw is None:
                    return None
                msg = json.loads(raw)
                if msg.get("topic") == "/robot_description":
                    return msg.get("msg", {}).get("data")
        except asyncio.TimeoutError:
            return None
        finally:
            conn.close()

    data = asyncio.run(fetch())
    if not data:
        raise CheckFailed(
            "rosbridge accepted the /robot_description subscription but delivered "
            "no URDF -- this is what the 3D viewer sees as 'No URDF received'"
        )
    log(f"URDF reached a websocket client through rosbridge ({len(data)} bytes)")


def main() -> int:
    if not (ROOT / "install" / "setup.bash").is_file():
        log("workspace not built")
        return 1

    import rclpy
    from rclpy.node import Node

    # Every assertion below is relative to this.
    log(f"discovery range: {os.environ.get('ROS_AUTOMATIC_DISCOVERY_RANGE', '<unset>')}")
    start_core()
    rclpy.init()
    node = Node("ci_core_bringup")
    failures: list[str] = []
    try:
        wait_for_bringup(node)
        # Let every participant announce before counting publishers.
        time.sleep(GRAPH_SETTLE_S)

        urdf = ""
        for check in (
            lambda: check_single_robot_description_publisher(node),
            lambda: check_robot_description_is_latched(node),
            lambda: check_controllers_active(),
            lambda: check_urdf_reaches_a_websocket_client(),
        ):
            try:
                check()
            except CheckFailed as exc:
                failures.append(str(exc))
                log(f"FAIL: {exc}")

        try:
            urdf = receive_urdf(node)
            check_meshes_resolve_locally(urdf)
        except CheckFailed as exc:
            failures.append(str(exc))
            log(f"FAIL: {exc}")

        if failures:
            dump_diagnostics()
    except CheckFailed as exc:
        log(f"FAIL: {exc}")
        failures.append(str(exc))
        dump_diagnostics()
    finally:
        node.destroy_node()
        rclpy.shutdown()
        stop_core()

    if failures:
        log(f"{len(failures)} check(s) failed")
        return 1
    log("OK — core came up and the graph is serviceable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
