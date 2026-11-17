#!/usr/bin/env python3

from __future__ import annotations

import re
import time

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


HEARTBEAT = """() => {
    window.__hb = { last: performance.now(), max: 0, n: 0 };
    setInterval(() => {
        const now = performance.now();
        window.__hb.max = Math.max(window.__hb.max, now - window.__hb.last);
        window.__hb.last = now;
        window.__hb.n++;
    }, 100);
}"""


def watch_model(page) -> dict:
    model: dict = {"replies": 0, "sent": 0, "diag": 0}
    page.add_init_script("(" + HEARTBEAT + ")()")

    def on_console(msg) -> None:
        if "MESHDIAG" in msg.text:
            model["diag"] += 1
            if model["diag"] % 20 == 0:
                log("DIAG browser: " + msg.text[:100])
        m = re.search(r"\[useRobotModel\] Done .* (\d+)/(\d+) meshes", msg.text)
        if m:
            model["meshes"] = (int(m.group(1)), int(m.group(2)))
            model["done_at"] = time.time()

    def on_frame(payload) -> None:
        head = payload[:120] if isinstance(payload, str) else ""
        if '"service_response"' in head and '"/mesh/get"' in head:
            model["replies"] += 1

    page.on("console", on_console)
    def on_sent(payload) -> None:
        if isinstance(payload, str) and '"call_service"' in payload[:120] and '"/mesh/get"' in payload[:200]:
            model["sent"] += 1

    page.on("websocket", lambda ws: (ws.on("framereceived", on_frame), ws.on("framesent", on_sent)))
    return model


def check_viewer(page, model: dict, opened_at: float) -> None:
    deadline = opened_at + MODEL_TIMEOUT_S
    seen, progressed_at = -1, time.time()
    while "meshes" not in model and time.time() < deadline and time.time() - progressed_at < MODEL_STALL_S:
        if model["replies"] != seen:
            seen, progressed_at = model["replies"], time.time()
        if int(time.time() - opened_at) % 10 == 0:
            try:
                hb = page.evaluate("() => ({ ...window.__hb, now: performance.now() })", )
            except Exception as e:
                hb = f"evaluate failed: {e}"[:120]
            log(f"DIAG t={time.time() - opened_at:.0f}s sent={model['sent']} replies={model['replies']} hb={hb}")
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
