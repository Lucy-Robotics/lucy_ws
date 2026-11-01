#!/usr/bin/env python3

from __future__ import annotations

import re

from ci_stack import MOVED_RAD, SAME_RAD, CheckFailed, Ros, diff, log

MOBILE_VIEWPORT = {"width": 390, "height": 844}
OUTSIDE_VIEWPORT = """() => {
    const clipped = (el) => {
        for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
            if (['auto', 'scroll'].includes(getComputedStyle(p).overflowX) && p.scrollWidth > p.clientWidth) return false;
        }
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && (r.left < -1 || r.right > innerWidth + 1);
    };
    const names = [...document.querySelectorAll('button, a, input, .ant-slider, canvas')].filter(clipped)
        .map((el) => (el.getAttribute('aria-label') || el.innerText || el.tagName).trim().slice(0, 30));
    return {scroll: document.documentElement.scrollWidth, width: innerWidth, names};
}"""


def check_fits_width(page, where: str) -> None:
    fit = page.evaluate(OUTSIDE_VIEWPORT)
    if fit["scroll"] > fit["width"] or fit["names"]:
        raise CheckFailed(
            f"mobile layout {where}: page {fit['scroll']}px wide on a {fit['width']}px screen, "
            f"controls outside it: {fit['names']}"
        )


def check_mobile(page, ros: Ros) -> None:
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.get_by_role("button", name="Show actions").wait_for()
    page.wait_for_timeout(1000)
    check_fits_width(page, "at load")
    log(f"panel switched to its mobile layout at {MOBILE_VIEWPORT['width']}x{MOBILE_VIEWPORT['height']}")

    page.get_by_role("button", name="Control Robot: OFF").click()
    page.locator(".ant-slider-disabled:visible").first.wait_for(timeout=15_000)
    check_fits_width(page, "with Control Robot OFF")
    page.get_by_role("button", name="Control Robot: ON").click()
    sliders = page.locator(".ant-slider:visible:not(.ant-slider-disabled)")
    sliders.first.wait_for(timeout=15_000)
    log("mobile Control Robot OFF and ON lock and unlock the sliders")

    start = ros.wait_settled()
    sliders.first.scroll_into_view_if_needed()
    box = sliders.first.bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2)
    ros.wait_for("the mobile slider's move", lambda s: diff(start, s) > MOVED_RAD)
    log("mobile slider moved the robot")

    page.get_by_role("button", name="Show actions").click()
    check_fits_width(page, "with the actions shown")
    page.get_by_role("button", name=re.compile(r"reset all", re.I)).first.click()
    ros.wait_for("RESET ALL from the mobile actions", lambda s: diff(start, s) < SAME_RAD)
    log("mobile RESET ALL settled the robot")

    canvas = max(page.locator("canvas").all(), key=lambda c: (lambda b: b["width"] * b["height"] if b else 0)(c.bounding_box()))
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    if not box or box["width"] < MOBILE_VIEWPORT["width"] / 2 or box["height"] < 100:
        raise CheckFailed(f"mobile 3D view is too small to use: {box}")
    log(f"mobile 3D view is {box['width']:.0f}x{box['height']:.0f}")
