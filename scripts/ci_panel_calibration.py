#!/usr/bin/env python3
"""Drive the calibration wizard end to end in a browser, against the simulated arm."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ci_stack import PANEL_PORT, ROOT, Ros, log

PACKAGE = ROOT / "src" / "so_arm101_urdf"
HARDWARE = PACKAGE / "config" / "hardware"
URDF = PACKAGE / "description" / "robot_description" / "urdf" / "robot_description.urdf.xacro"
GENERATED = [
    URDF,
    PACKAGE / "description" / "ros2_control" / "so_arm101_ros2_control.xacro",
    PACKAGE / "config" / "controllers.yaml",
]
PRESET = "so101_SIMULATED"
SWEEP_MS = 2300  # One whole period of the simulated arm's sweep.
ACTIVATE_TIMEOUT_MS = 240_000


class Restored:
    """Put the hardware config back afterwards: a developer's calibration may be in there."""

    def __enter__(self) -> "Restored":
        self._dir = Path(tempfile.mkdtemp(prefix="lucy_calibration_e2e_"))
        shutil.copytree(HARDWARE, self._dir / "hardware")
        for i, path in enumerate(GENERATED):
            shutil.copy2(path, self._dir / f"{i}")
        return self

    def __exit__(self, *_exc) -> None:
        shutil.rmtree(HARDWARE)
        shutil.copytree(self._dir / "hardware", HARDWARE)
        for i, path in enumerate(GENERATED):
            shutil.copy2(self._dir / f"{i}", path)
        shutil.rmtree(self._dir)
        log("restored the hardware config")


def refuse_real_hardware() -> None:
    """This test turns torque on. It must never run against a real arm."""
    found = subprocess.run(
        ["pgrep", "-f", "[l]ucy-embedded-firmware-linux"], capture_output=True, text=True, check=False
    )
    if found.stdout.strip():
        raise RuntimeError("the host firmware is running: this test only runs with real:=false")


def phase(page, name: str, timeout_ms: int = 30_000):
    return page.locator(f'[data-testid="calibration-wizard"][data-phase="{name}"]').wait_for(
        timeout=timeout_ms
    )


def button(page, name: str):
    return page.get_by_role("button", name=re.compile(f"^{name}$", re.I))


def check_calibration(page, ros: Ros) -> None:
    from playwright.sync_api import expect

    refuse_real_hardware()
    with Restored():
        # Leaving the control page ends that client, and its control with it.
        page.goto(f"http://127.0.0.1:{PANEL_PORT}/robot-configuration")
        ros.wait_for("Control Robot off", lambda _s: not ros.active_client, timeout_s=20)
        phase(page, "idle", 60_000)
        log("wizard shows on the configuration page")

        button(page, "Start calibration").click()
        phase(page, "mid_pose")
        expect(button(page, "The arm is in this pose")).to_be_enabled(timeout=15_000)
        log("health checks pass on the simulated arm")

        page.get_by_role("tab", name="Hardware YAML").click()
        page.get_by_role("tab", name="Calibrate").click()
        phase(page, "mid_pose")

        button(page, "The arm is in this pose").click()
        phase(page, "joints")
        log("homed")

        # Each joint records as soon as it is shown; one action accepts it and moves on.
        heading = page.locator('[data-testid="calibration-wizard"] h4')
        for i in range(6):
            joint = heading.inner_text()
            accept = button(page, "Accept and continue")
            expect(accept).to_be_enabled(timeout=10_000)
            page.wait_for_timeout(SWEEP_MS)
            if i == 0:
                page.locator("body").click(position={"x": 1, "y": 1})  # Nothing focused.
                page.keyboard.press("Enter")
            else:
                accept.click()
            if i < 5:
                expect(heading).not_to_have_text(joint, timeout=10_000)
        phase(page, "review")
        log("all six joints recorded")

        button(page, "Save preset").click()
        phase(page, "applied")
        preset = HARDWARE / "configs" / f"{PRESET}.yaml"
        sibling = HARDWARE / "configs" / f"{PRESET}.lerobot.json"
        if not preset.is_file() or not sibling.is_file():
            raise RuntimeError(f"apply did not write {preset} and {sibling}")
        if "adapter_serial: SIMULATED" not in preset.read_text(encoding="utf-8"):
            raise RuntimeError("the preset does not name the adapter")
        if len(json.loads(sibling.read_text(encoding="utf-8"))) != 6:
            raise RuntimeError("the LeRobot file does not have six motors")
        log("preset and LeRobot file written")

        before = URDF.read_text(encoding="utf-8")
        button(page, "Activate and reload").click()
        # Once activated, the wizard closes the session and hands over to the control page.
        page.wait_for_url(f"http://127.0.0.1:{PANEL_PORT}/", timeout=ACTIVATE_TIMEOUT_MS)
        if URDF.read_text(encoding="utf-8") == before:
            raise RuntimeError("activating the preset did not update the URDF limits")
        log("activated: limits regenerated, the stack reloaded, control page shown")
        page.screenshot(path=str(ROOT / "log" / "panel_calibration_e2e_so_arm101.png"), full_page=True)

        ros.wait_settled()
        if ros.active_client:
            raise RuntimeError("finishing calibration turned Control Robot on")
        page.goto(f"http://127.0.0.1:{PANEL_PORT}/robot-configuration")
        phase(page, "idle")
        log("calibration finished, torque still off")
