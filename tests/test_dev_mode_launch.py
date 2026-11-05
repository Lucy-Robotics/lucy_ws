"""Developer mode runs the saved launch with vite dev; production runs the built panel."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install  # noqa: E402
from launcher import autostart as autostart_module  # noqa: E402
from launcher.apply import _package_needs_vite_preserve  # noqa: E402
from launcher.state import LauncherState  # noqa: E402

CONFIG = {
    "packages": [
        {"id": "core", "name": "Core", "type": "core", "dependencies": [], "conflicts": [],
         "command": "ros2 launch lucy_bringup lucy.launch.py"},
        {"id": "robot_a", "name": "Robot A", "type": "modifier", "dependencies": ["core"],
         "conflicts": [], "command": "robot_package:=a_urdf", "requires_pkg": "a_urdf"},
        {"id": "control_panel", "name": "Control Panel", "type": "service", "dependencies": [],
         "conflicts": [], "command": "pixi run panel-prod", "dev_command": "pixi run panel-dev"},
        {"id": "teleop", "name": "Teleop", "type": "service", "dependencies": ["core"],
         "conflicts": [], "command": "ros2 run teleop node"},
    ]
}


def _state(monkeypatch, dev_mode):
    monkeypatch.setattr("launcher.state.load_state", lambda: {"modifiers": []})
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: dev_mode)
    monkeypatch.setattr("launcher.package._ros_pkg_installed", lambda _name: True)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    return LauncherState(CONFIG)


@pytest.fixture
def launched(monkeypatch):
    calls = {"applied": 0, "saved": None}
    monkeypatch.setattr(autostart_module, "apply_changes",
                        lambda _s: calls.__setitem__("applied", calls["applied"] + 1))
    monkeypatch.setattr(autostart_module, "save_selection",
                        lambda ids: calls.__setitem__("saved", ids))
    return calls


@pytest.mark.parametrize("dev_mode, command", [(True, "pixi run panel-dev"), (False, "pixi run panel-prod")])
def test_control_panel_command_follows_the_mode(monkeypatch, dev_mode, command):
    assert _state(monkeypatch, dev_mode).get_by_id("control_panel").command == command


def test_dev_mode_starts_the_saved_launch(monkeypatch, launched):
    state = _state(monkeypatch, True)
    monkeypatch.setattr(autostart_module, "load_selection", lambda: {"core", "teleop"})
    state.get_by_id("core").selected = True
    state.get_by_id("teleop").selected = True

    assert autostart_module.autostart(state, True)
    assert launched == {"applied": 1, "saved": {"core", "teleop"}}


def test_dev_mode_without_saved_launch_starts_nothing(monkeypatch, launched):
    state = _state(monkeypatch, True)
    monkeypatch.setattr(autostart_module, "load_selection", lambda: None)

    assert autostart_module.autostart(state, True) is None
    assert launched == {"applied": 0, "saved": None}


def test_production_starts_core_robot_and_panel(monkeypatch, launched):
    state = _state(monkeypatch, False)

    assert autostart_module.autostart(state, False)
    assert launched["applied"] == 1
    assert launched["saved"] == {"core", "robot_a", "control_panel"}


def test_production_panel_survives_restarts(monkeypatch):
    assert _package_needs_vite_preserve(_state(monkeypatch, False).get_by_id("control_panel"))


@pytest.mark.parametrize("developer, builds_panel", [(True, False), (False, True)])
def test_install_builds_the_panel_outside_developer_mode(monkeypatch, developer, builds_panel):
    commands = []
    monkeypatch.setattr(install, "build_local_realsense_optional", lambda *a, **k: None)
    monkeypatch.setattr(install, "setup_firmware_toolchain", lambda *a, **k: None)

    install.build_workspace("/ws", lambda cmd, **_k: commands.append(cmd) or 0,
                            lambda _m: None, developer=developer)

    assert any(cmd[-1] == "panel-build" for cmd in commands) == builds_panel
