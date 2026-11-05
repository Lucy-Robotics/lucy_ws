"""The panel address is a pick-one option shown under the panel row, applied by restarting it."""

import launcher
from launcher import options as options_module
from launcher.apply import apply_changes
from launcher.options import with_focused_options
from launcher.state import LauncherState, _has_unapplied_changes, _intended_running, _pkg_start_times

CONFIG = {
    "packages": [
        {"id": "control_panel", "name": "Control Panel", "type": "interface", "dependencies": [],
         "conflicts": [], "command": "pixi run panel-prod"},
        {"id": "panel_host_local", "name": "This computer only", "type": "option",
         "parent": "control_panel", "conflicts": ["panel_host_network"], "command": "--host 127.0.0.1"},
        {"id": "panel_host_network", "name": "Every network", "type": "option", "parent": "control_panel",
         "conflicts": ["panel_host_local"], "command": "--host 0.0.0.0", "default_on": True},
        {"id": "lucy_cli", "name": "Lucy CLI", "type": "interface", "dependencies": [],
         "conflicts": [], "command": "ros2 run lucy_cli tui"},
    ]
}


def _state(monkeypatch, tmp_path, launched=()):
    options_file = tmp_path / "options.json"
    options_file.write_text(str(list(launched)).replace("'", '"'))
    monkeypatch.setattr(options_module, "OPTIONS_FILE", options_file)
    monkeypatch.setattr("launcher.state.load_state", lambda: {"modifiers": []})
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: False)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    monkeypatch.setattr("launcher.package.run_shell_command", lambda *_a, **_k: bool(launched))
    _pkg_start_times.clear()
    _intended_running.clear()
    return LauncherState(CONFIG)


def _ids(state, focused):
    interfaces = [p for p in state.packages if p.type == "interface"]
    return [p.id for p in with_focused_options(interfaces, state.packages, focused)]


def test_options_show_only_while_the_panel_or_an_option_has_the_cursor(monkeypatch, tmp_path):
    state = _state(monkeypatch, tmp_path)
    assert _ids(state, "lucy_cli") == ["control_panel", "lucy_cli"]
    expanded = ["control_panel", "panel_host_local", "panel_host_network", "lucy_cli"]
    assert _ids(state, "control_panel") == expanded
    assert _ids(state, "panel_host_local") == expanded


def test_one_address_stays_picked(monkeypatch, tmp_path):
    state = _state(monkeypatch, tmp_path)
    assert state.toggle("panel_host_network") == "Pick another option instead"
    state.toggle("panel_host_local")
    assert state.get_by_id("panel_host_local").selected
    assert not state.get_by_id("panel_host_network").selected


def test_changing_the_address_restarts_the_panel_with_it(monkeypatch, tmp_path):
    state = _state(monkeypatch, tmp_path, launched=["panel_host_network"])
    commands, stopped = [], []
    monkeypatch.setattr(launcher, "set_orphan_preserve_windows", lambda *_a, **_k: None)
    monkeypatch.setattr(launcher, "run_shell_command", lambda _cmd, **_k: None)
    monkeypatch.setattr(launcher, "_stop_tmux_window", stopped.append)
    monkeypatch.setattr(launcher, "_tmux_new_pixi_window", lambda _w, cmd, **_k: commands.append(cmd))
    panel = state.get_by_id("control_panel")
    assert panel.is_running and not _has_unapplied_changes(state)

    state.toggle("panel_host_local")
    assert _has_unapplied_changes(state)
    apply_changes(state)

    assert stopped == ["control_panel"]
    assert commands == ["pixi run panel-prod --host 127.0.0.1"]
    assert options_module.launched_options() == {"panel_host_local"}
