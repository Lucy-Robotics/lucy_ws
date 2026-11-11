"""The launcher TUI's ROS domain counter: bounds, persistence, and restart on change."""

import os

import pytest

import launcher
from launcher import config
from launcher.apply import apply_changes, restore_selection
from launcher.domain import MAX_DOMAIN_ID, parse_domain_id, step_domain_id
from launcher.state import LauncherState, _has_unapplied_changes

CONFIG = {
    "packages": [
        {
            "id": "core",
            "name": "Core",
            "type": "core",
            "command": "ros2 launch lucy_bringup lucy.launch.py",
        },
        {
            "id": "lucy_cli",
            "name": "Lucy CLI",
            "type": "interface",
            "dependencies": ["core"],
            "command": "ros2 run lucy_cli tui",
        },
        {
            "id": "control_panel",
            "name": "Control Panel",
            "type": "interface",
            "command": "pixi run panel-dev",
        },
    ]
}


@pytest.mark.parametrize(
    "raw, domain",
    [("0", 0), (" 7 ", 7), (42, 42), (str(MAX_DOMAIN_ID), MAX_DOMAIN_ID),
     (str(MAX_DOMAIN_ID + 1), None), ("-1", None), ("abc", None), ("", None), (None, None)],
)
def test_parse_domain_id(raw, domain):
    assert parse_domain_id(raw) == domain


def test_counter_stays_in_range():
    assert step_domain_id(0, -1) == 0
    assert step_domain_id(0, 1) == 1
    assert step_domain_id(MAX_DOMAIN_ID, 1) == MAX_DOMAIN_ID


def _state(monkeypatch, running_state=None, running=()):
    monkeypatch.setattr(
        "launcher.state.load_state", lambda: running_state or {"modifiers": []}
    )
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: False)
    monkeypatch.setattr("launcher.package._ros_pkg_installed", lambda _name: True)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    state = LauncherState(CONFIG)
    for pkg in state.packages:
        pkg.is_running = pkg.id in running
        pkg.selected = pkg.id in running
    return state


def test_domain_defaults_to_the_environment(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "5")
    assert _state(monkeypatch).domain_id == 5


def test_running_core_shows_its_domain(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "5")
    state = _state(monkeypatch, {"modifiers": [], "domain_id": 3}, running={"core"})
    assert state.domain_id == state.running_domain_id == 3
    assert not state.domain_restart_pending()


def test_changing_the_domain_of_a_running_core_is_unapplied(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "0")
    state = _state(monkeypatch, running={"core"})
    state.step_domain(1)
    assert state.domain_restart_pending()
    assert _has_unapplied_changes(state)
    state.step_domain(-1)
    assert not state.domain_restart_pending()


def test_changing_the_domain_without_core_needs_no_restart(monkeypatch):
    state = _state(monkeypatch)
    state.step_domain(4)
    assert not state.domain_restart_pending()


@pytest.fixture
def selection_file(monkeypatch, tmp_path):
    path = tmp_path / "selection.json"
    monkeypatch.setattr(config, "SELECTION_FILE", path)
    return path


def test_selection_keeps_the_domain(selection_file):
    config.save_selection({"core", "lucy_cli"}, 7)
    assert config.load_selection() == {"core", "lucy_cli"}
    assert config.load_selected_domain_id() == 7


def test_restore_uses_the_saved_domain_when_core_is_stopped(monkeypatch, selection_file):
    config.save_selection({"core"}, 9)
    state = _state(monkeypatch)
    restore_selection(state)
    assert state.domain_id == 9


def test_restore_keeps_the_domain_of_a_running_core(monkeypatch, selection_file):
    config.save_selection({"core"}, 9)
    state = _state(monkeypatch, {"modifiers": [], "domain_id": 2}, running={"core"})
    restore_selection(state)
    assert state.domain_id == 2


def test_apply_restarts_core_and_ros_windows_in_the_new_domain(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "0")
    state = _state(monkeypatch, running={"core", "lucy_cli", "control_panel"})
    state.step_domain(3)

    calls, saved = [], []
    monkeypatch.setattr(launcher, "_stop_core_tmux", lambda: calls.append("stop core"))
    monkeypatch.setattr(
        launcher, "_stop_tmux_window", lambda pid: calls.append(f"stop {pid}")
    )
    monkeypatch.setattr(launcher, "_finish_teardown", lambda **_kw: None)
    monkeypatch.setattr(launcher, "save_state", saved.append)
    monkeypatch.setattr(launcher, "run_shell_command", calls.append)

    apply_changes(state)

    assert "stop core" in calls and "stop lucy_cli" in calls
    assert "stop control_panel" not in calls  # talks to rosbridge, not DDS
    starts = [c for c in calls if c.startswith("tmux new-window")]
    assert any("-n core" in c and "domain_id:=3" in c for c in starts)
    assert any("-n lucy_cli" in c and "ROS_DOMAIN_ID=3" in c for c in starts)
    assert saved[-1] == {"modifiers": [], "domain_id": 3}
    assert os.environ["ROS_DOMAIN_ID"] == "3"
    assert state.running_domain_id == 3
    assert not state.domain_restart_pending()
