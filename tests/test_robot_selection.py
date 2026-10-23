"""Robot modifiers must stay a required exclusive group in the launcher TUI."""

from launcher.state import LauncherState


CONFIG = {
    "packages": [
        {
            "id": "core",
            "name": "Core",
            "type": "core",
            "dependencies": [],
            "conflicts": [],
            "command": "ros2 launch lucy_bringup lucy.launch.py",
        },
        {
            "id": "robot_a",
            "name": "Robot A",
            "type": "modifier",
            "dependencies": ["core"],
            "conflicts": ["robot_b"],
            "command": "robot_package:=a_urdf",
            "requires_pkg": "a_urdf",
        },
        {
            "id": "robot_b",
            "name": "Robot B",
            "type": "modifier",
            "dependencies": ["core"],
            "conflicts": ["robot_a"],
            "command": "robot_package:=b_urdf",
            "requires_pkg": "b_urdf",
        },
        {
            "id": "gazebo",
            "name": "Gazebo",
            "type": "modifier",
            "dependencies": ["core"],
            "conflicts": [],
            "command": "gazebo:=true",
        },
    ]
}


def _state(monkeypatch):
    monkeypatch.setattr("launcher.state.load_state", lambda: {"modifiers": []})
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: False)
    monkeypatch.setattr("launcher.package._ros_pkg_installed", lambda _name: True)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    return LauncherState(CONFIG)


def test_cannot_untick_the_last_robot(monkeypatch):
    state = _state(monkeypatch)
    state.toggle("robot_a")
    assert state.get_by_id("robot_a").selected

    err = state.toggle("robot_a")
    assert err == "One robot package required"
    assert state.get_by_id("robot_a").selected
    assert not state.get_by_id("robot_b").selected


def test_switching_robots_keeps_exactly_one(monkeypatch):
    state = _state(monkeypatch)
    state.toggle("robot_a")
    state.toggle("robot_b")

    assert not state.get_by_id("robot_a").selected
    assert state.get_by_id("robot_b").selected

    err = state.toggle("robot_b")
    assert err == "One robot package required"
    assert state.get_by_id("robot_b").selected


def test_non_robot_modifiers_still_toggle_off(monkeypatch):
    state = _state(monkeypatch)
    state.toggle("gazebo")
    assert state.get_by_id("gazebo").selected
    assert state.toggle("gazebo") is None
    assert not state.get_by_id("gazebo").selected


def test_save_selection_replaces_unwritable_file(monkeypatch, tmp_path):
    from launcher import config

    # Stands in for the root-owned .lucy_launcher_state.json the Docker setup left behind.
    stale = tmp_path / ".lucy_launcher_state.json"
    stale.write_text('{"selected": ["robot_a"]}')
    stale.chmod(0o444)
    monkeypatch.setattr(config, "SELECTION_FILE", stale)

    config.save_selection({"core", "robot_b"})

    assert config.load_selection() == {"core", "robot_b"}
