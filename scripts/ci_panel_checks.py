#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import time

from ci_panel_calibration import check_calibration
from ci_panel_viewer import WEBGL_RENDERER, check_viewer, check_viewer_follows, watch_model
from ci_stack import PANEL_PORT, ROOT, Ros, diff, log

MOVED_RAD = 0.05
SAME_RAD = 0.02


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

    modal.get_by_role("button", name="CREATE ANIMATION").click()
    modal.get_by_placeholder("Animation name").fill("ci_anim")
    modal.get_by_role("button", name="plus ci_b", exact=True).click()
    modal.get_by_role("button", name="plus ci_a", exact=True).click()
    modal.get_by_role("button", name="Loop: OFF").click()
    modal.get_by_role("button", name="SAVE ANIMATION").click()
    modal.locator(".ant-list-item").filter(has_text="ci_anim").get_by_role("button", name="PLAY").click()
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
            if robot == "so_arm101_urdf":
                check_calibration(page, ros)
        finally:
            shot.parent.mkdir(exist_ok=True)
            page.mouse.move(0, 0)
            page.screenshot(path=str(shot), full_page=True)
            log(f"screenshot: {shot}")
            browser.close()
    log(f"panel drove {robot}")
