"""Workspace-root unit tests (launcher helpers, install config)."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


@pytest.fixture
def isolated_state(monkeypatch):
    import json

    from launcher import state as state_module
    from launcher.state import LauncherState

    for tracked in (
        state_module._pkg_stop_times,
        state_module._pkg_start_times,
        state_module._intended_running,
    ):
        tracked.clear()

    config = json.loads((ROOT / "config" / "launcher_config.json").read_text())
    for target, value in {
        "launcher.state.load_state": lambda: {"modifiers": []},
        "launcher.state.get_dev_mode": lambda: False,
        "launcher.state.tmux_window_snapshot": lambda: (set(), {}),
        "launcher.package._ros_pkg_installed": lambda _name: True,
        "launcher.package._pane_exit_status": lambda _pkg_id: None,
        "launcher.package.run_shell_command": lambda *_a, **_k: False,
    }.items():
        monkeypatch.setattr(target, value)

    return LauncherState(config)
