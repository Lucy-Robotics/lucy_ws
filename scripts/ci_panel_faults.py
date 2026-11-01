#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import time

from ci_stack import PANEL_PORT, CheckFailed, Ros, log

RECONNECT_TIMEOUT_S = 30.0
AGREE_TIMEOUT_S = 15.0
RELEASE_TIMEOUT_S = 15.0
ENABLED_SLIDER = ".ant-slider:not(.ant-slider-disabled)"


def wait_until(page, what: str, ok, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while not ok():
        if time.time() > deadline:
            raise CheckFailed(f"{what} within {timeout_s:.0f}s")
        page.wait_for_timeout(500)


def open_panel(context, sockets: list):
    page = context.new_page()
    page.on("console", lambda m: m.type == "error" and log(f"browser: {m.text}"))

    def forward(ws) -> None:
        ws.connect_to_server()
        sockets.append(ws)

    page.route_web_socket("**/rosbridge", forward)
    page.add_init_script("localStorage.setItem('gettingStartedCompleted', 'true')")
    page.goto(f"http://127.0.0.1:{PANEL_PORT}/")
    page.locator(".ant-slider").first.wait_for(timeout=120_000)
    return page


def take_control(page, ros: Ros) -> str:
    page.get_by_role("button", name=re.compile(r"^Control Robot(: ON)?$")).first.click()
    page.locator(ENABLED_SLIDER).first.wait_for(timeout=30_000)
    wait_until(page, "the registry never gave the panel the lease", lambda: bool(ros.active_client), RELEASE_TIMEOUT_S)
    return ros.active_client


def switch_shows_on(page) -> bool:
    on_button = page.get_by_role("button", name="Control Robot: ON").first
    return "on" in (on_button.get_attribute("class") or "").split()


def check_switch_after_drop(page, ros: Ros, sockets: list) -> None:
    holder = take_control(page, ros)
    for ws in list(sockets):
        ws.close()
    sockets.clear()
    log("dropped the panel's rosbridge socket while it held control")
    wait_until(page, "the panel did not reconnect", lambda: bool(sockets), RECONNECT_TIMEOUT_S)
    page.locator(".ant-slider").first.wait_for(timeout=int(RECONNECT_TIMEOUT_S * 1000))
    wait_until(
        page,
        "Control Robot never matched the lease after the reconnect",
        lambda: switch_shows_on(page) == (ros.active_client == holder),
        AGREE_TIMEOUT_S,
    )
    log(f"after the reconnect Control Robot shows {'ON' if switch_shows_on(page) else 'OFF'}, matching the lease")


def check_tab_close_releases(page, ros: Ros) -> None:
    if not switch_shows_on(page):
        take_control(page, ros)
    watcher = page.context.new_page()
    page.close()
    wait_until(watcher, "closing the panel tab did not release control", lambda: not ros.active_client, RELEASE_TIMEOUT_S)
    log("closing the panel tab released control")


def exercise_faults(ros: Ros) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("LUCY_E2E_BROWSER") or None)
        try:
            sockets: list = []
            page = open_panel(browser.new_context(viewport={"width": 1600, "height": 1000}), sockets)
            check_switch_after_drop(page, ros, sockets)
            check_tab_close_releases(page, ros)
        finally:
            browser.close()
