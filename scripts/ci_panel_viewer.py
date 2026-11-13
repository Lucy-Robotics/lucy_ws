#!/usr/bin/env python3

from __future__ import annotations

import re
import time
from collections import Counter

from ci_stack import CheckFailed, Ros, log

MODEL_TIMEOUT_S = 600.0
MODEL_STALL_S = 30.0
FOLLOW_TIMEOUT_S = 60.0
URDF_HINT_S = 25.0
WEBGL_RENDERER = """() => {
    const gl = document.createElement('canvas').getContext('webgl');
    const info = gl && gl.getExtension('WEBGL_debug_renderer_info');
    return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl ? 'unknown' : 'none';
}"""
VIEWER_ERRORS = re.compile(r"No URDF received|Could not load any meshes|WebGL is not supported|Failed to load robot model")


MESH_CALL_ID = re.compile(r'"id":\s*"(call_service:/mesh/get:\d+)"')
FRAME_OP = re.compile(r'"op":\s*"(\w+)"')
FRAME_NAME = re.compile(r'"(?:topic|service)":\s*"([^"]+)"')


def frame_key(direction: str, payload) -> str:
    head = payload[:300] if isinstance(payload, str) else ""
    op, name = FRAME_OP.search(head), FRAME_NAME.search(head)
    return f"{direction} {op.group(1) if op else '?'} {name.group(1) if name else '?'}"


def watch_model(page) -> dict:
    model: dict = {"replies": 0}
    started_at, sent_at, waits = time.time(), {}, []
    frames, frame_bytes = Counter(), Counter()

    def count(direction: str, payload) -> None:
        key = frame_key(direction, payload)
        frames[key] += 1
        frame_bytes[key] += len(payload)

    def on_sent(payload) -> None:
        count("tx", payload)
        m = MESH_CALL_ID.search(payload[:300]) if isinstance(payload, str) else None
        if m:
            sent_at[m.group(1)] = time.time()

    def on_console(msg) -> None:
        m = re.search(r"\[useRobotModel\] Done .* (\d+)/(\d+) meshes", msg.text)
        if m:
            model["meshes"] = (int(m.group(1)), int(m.group(2)))
            model["done_at"] = time.time()

    def on_frame(payload) -> None:
        count("rx", payload)
        head = payload[:120] if isinstance(payload, str) else ""
        if '"service_response"' in head and '"/mesh/get"' in head:
            model["replies"] += 1
            m = MESH_CALL_ID.search(payload[:300]) or MESH_CALL_ID.search(payload[-300:])
            if m and m.group(1) in sent_at:
                waits.append(time.time() - sent_at.pop(m.group(1)))
            if model["replies"] % 25 == 0:
                log(
                    f"mesh/get at {time.time() - started_at:.0f}s: {model['replies']} replies, "
                    f"{len(sent_at)} pending, reply wait max {max(waits, default=0):.1f}s "
                    f"mean {sum(waits) / max(len(waits), 1):.1f}s ({len(payload) // 1024} KiB)"
                )
                waits.clear()
                log("frames: " + ", ".join(f"{k} x{n} {frame_bytes[k] // 1024}KiB" for k, n in frames.most_common(8)))
                frames.clear()
                frame_bytes.clear()

    page.on("console", on_console)
    page.on("websocket", lambda ws: (ws.on("framereceived", on_frame), ws.on("framesent", on_sent)))
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


def grab(page, canvas) -> bytes:
    return page.screenshot(clip=canvas.bounding_box(), timeout=FOLLOW_TIMEOUT_S * 1000)


def check_viewer_follows(page, ros: Ros) -> None:
    canvas = max(page.locator("canvas").all(), key=lambda c: (lambda b: b["width"] * b["height"] if b else 0)(c.bounding_box()))
    before = grab(page, canvas)
    page.get_by_role("button", name=re.compile(r"reset all", re.I)).first.click()
    ros.wait_settled()
    deadline = time.time() + FOLLOW_TIMEOUT_S
    while grab(page, canvas) == before:
        if time.time() > deadline:
            raise CheckFailed(f"the 3D view did not change within {FOLLOW_TIMEOUT_S:.0f}s of RESET ALL moving the joints")
        page.wait_for_timeout(1000)
    log("3D view follows the joints")
