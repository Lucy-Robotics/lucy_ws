import json
from pathlib import Path

import pytest

from launcher import tui
from launcher.state import LauncherState

CONFIG = json.loads(
    (
        Path(__file__).resolve().parents[1] / "config" / "launcher_config.json"
    ).read_text()
)


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, size):
        self.size = size
        self.rows = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.rows = []

    def refresh(self):
        pass

    def addstr(self, y, x, text, *_):
        self.rows.append((y, text))


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(tui, "curses", _Curses())
    monkeypatch.setattr("launcher.state.load_state", lambda: {"modifiers": []})
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: False)
    monkeypatch.setattr("launcher.package._ros_pkg_installed", lambda _name: True)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    return LauncherState(CONFIG)


def _row(screen, needle):
    return next(y for y, text in screen.rows if needle in text)


def _min_height(state):
    pkgs = state.packages
    robots = [p for p in pkgs if p.type == "modifier" and p.requires_pkg]
    primary = (
        [p for p in pkgs if p.type == "core"]
        + [None]
        + [
            p
            for p in pkgs
            if p.type == "modifier" and not p.requires_pkg and p.section != "tools"
        ]
    )
    interfaces = [p for p in pkgs if p.type == "interface"]
    tools = [p for p in pkgs if p.type == "tool" or p.section == "tools"]
    sections = (
        [primary, robots, interfaces, tools] if robots else [primary, interfaces, tools]
    )
    return max(tui.MIN_TERM_HEIGHT, sum(len(s) + 2 for s in sections) + 3)


def test_domain_row_is_drawn_right_after_core(state):
    screen = _Screen((80, 120))
    tui.draw_tui(screen, state, 0, None, None)
    assert _row(screen, "ROS domain ID") == _row(screen, "Core") + 1


def test_visualizer_is_listed_under_tools(state):
    screen = _Screen((80, 120))
    tui.draw_tui(screen, state, 0, None, None)
    assert _row(screen, "Visualizer") > _row(screen, "Tools")


def test_one_row_below_minimum_height_draws_too_small_message(state):
    needed = _min_height(state)
    screen = _Screen((needed - 1, 120))
    assert tui.draw_tui(screen, state, 0, None, None) is None
    assert any(
        text == f"({tui.MIN_TERM_WIDTH}x{needed} required)" for _, text in screen.rows
    )


def test_minimum_height_draws_without_error(state):
    screen = _Screen((_min_height(state), 120))
    assert tui.draw_tui(screen, state, 0, None, None) is not None
