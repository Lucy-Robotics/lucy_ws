import json
from pathlib import Path

import pytest

from launcher.choices import settle_selection
from launcher.state import LauncherState

CONFIG = json.loads(
    (
        Path(__file__).resolve().parents[1] / "config" / "launcher_config.json"
    ).read_text()
)


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr("launcher.state.load_state", lambda: {"modifiers": []})
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: False)
    monkeypatch.setattr("launcher.package._ros_pkg_installed", lambda _name: True)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    return LauncherState(CONFIG)


def _on(state):
    return {p.id for p in state.packages if p.selected}


def _launch_args(state):
    return " ".join(
        p.command
        for p in state.packages
        if p.type == "modifier" and p.selected and not p.requires_pkg and p.command
    )


def test_ticking_core_ticks_simulator(state):
    state.toggle("core")
    assert "simulator" in _on(state)
    assert not _on(state) & {"gazebo", "hardware", "real_linux", "real_mcu_bridge"}


def test_ticking_hardware_ticks_micro_controllers(state):
    state.toggle("core")
    state.toggle("hardware")
    assert {"hardware", "real_mcu_bridge"} <= _on(state)
    assert "simulator" not in _on(state)


def test_ticking_usb_servos_switches_hardware_type(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("real_linux")
    assert "real_linux" in _on(state)
    assert "real_mcu_bridge" not in _on(state)


def test_unticking_only_mode_is_refused(state):
    state.toggle("core")
    assert state.toggle("simulator") == "One launch mode required"
    assert state.get_by_id("simulator").selected


def test_unticking_only_hardware_type_is_refused(state):
    state.toggle("core")
    state.toggle("hardware")
    assert state.toggle("real_mcu_bridge") == "One hardware type required"
    assert state.get_by_id("real_mcu_bridge").selected


def test_switching_to_hardware_unticks_headless(state):
    state.toggle("core")
    state.toggle("gazebo")
    state.toggle("headless")
    assert "headless" in _on(state)
    state.toggle("hardware")
    assert not _on(state) & {"gazebo", "headless"}


def test_ticking_hardware_type_in_simulator_selects_hardware(state):
    state.toggle("core")
    state.toggle("real_linux")
    assert {"hardware", "real_linux"} <= _on(state)
    assert "simulator" not in _on(state)


def test_settle_drops_bridge_without_hardware_and_picks_simulator(state):
    for pkg_id in ("core", "real_linux"):
        state.get_by_id(pkg_id).selected = True
    settle_selection(state)
    assert "real_linux" not in _on(state)
    assert "simulator" in _on(state)


def test_unticking_core_clears_all_modes(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("core")
    assert not _on(state) & {"simulator", "hardware", "real_mcu_bridge"}


def test_reticking_core_picks_simulator_again(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("core")
    state.toggle("core")
    assert "simulator" in _on(state)
    assert "hardware" not in _on(state)


def test_hardware_usb_servos_launch_arguments(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("real_linux")
    assert _launch_args(state) == "mode:=real bridge:=linux"


def test_default_launch_arguments(state):
    state.toggle("core")
    assert _launch_args(state) == "mode:=mock"


def test_physics_headless_launch_arguments(state):
    state.toggle("core")
    state.toggle("gazebo")
    state.toggle("headless")
    assert _launch_args(state) == "mode:=sim headless:=true"


def test_enabling_hardware_unticks_headless_without_settling(state):
    for pkg_id in ("core", "gazebo", "headless"):
        state.get_by_id(pkg_id).selected = True
    state._enable(state.get_by_id("hardware"))
    assert not state.get_by_id("headless").selected
