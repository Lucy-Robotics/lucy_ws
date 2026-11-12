import pytest

import launcher
from launcher import choices, domain_field, links, sections, tui
from launcher.state import _has_unapplied_changes


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self):
        self.writes = []

    def getmaxyx(self):
        return (80, 120)

    def erase(self):
        self.writes = []

    def refresh(self):
        pass

    def addstr(self, y, x, text, attr=0):
        self.writes.append((y, x, text, attr))


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links, sections):
        monkeypatch.setattr(module, "curses", _Curses())
    monkeypatch.setenv("ROS_DOMAIN_ID", "0")
    return isolated_state


@pytest.fixture
def shell(monkeypatch):
    calls = []
    monkeypatch.setattr(
        launcher, "run_shell_command", lambda c, *a, **k: calls.append(c)
    )
    monkeypatch.setattr(
        launcher, "run_shell_command_async", lambda c, **k: calls.append(c)
    )
    monkeypatch.setattr(launcher, "set_orphan_preserve_windows", lambda *a, **k: None)
    monkeypatch.setattr(launcher, "save_state", lambda _d: None)
    monkeypatch.setattr(launcher, "_stop_core_tmux", lambda: calls.append("stop core"))
    monkeypatch.setattr(launcher, "_finish_teardown", lambda **k: None)
    return calls


def _core_off_with_robot(state):
    state.toggle("core")
    state.toggle("robot_so_arm101")
    state.toggle("core")
    return state.get_by_id("robot_so_arm101")


def test_a_kept_modifier_is_not_active_while_core_is_off(state):
    robot = _core_off_with_robot(state)
    assert robot.selected
    assert not choices.is_active(state, robot)


def test_a_kept_modifier_is_active_with_core_on(state):
    robot = _core_off_with_robot(state)
    state.toggle("core")
    assert choices.is_active(state, robot)


def test_a_nested_modifier_is_inactive_when_any_ancestor_is_off(state):
    state.toggle("core")
    state.toggle("hardware")
    state.toggle("core")
    state.get_by_id("hardware").selected = False
    assert not choices.is_active(state, state.get_by_id("real_mcu_bridge"))


def test_apply_does_not_start_a_kept_modifier_while_core_is_off(state, shell):
    robot = _core_off_with_robot(state)
    launcher.apply_changes(state)
    assert not robot.is_running
    assert shell == []


def test_apply_stops_a_running_modifier_that_is_not_active(state, shell):
    robot = _core_off_with_robot(state)
    robot.is_running = True
    launcher.apply_changes(state)
    assert not robot.is_running


def test_kept_modifiers_while_core_is_off_are_not_unapplied_changes(state):
    _core_off_with_robot(state)
    assert not _has_unapplied_changes(state)


def test_an_active_package_that_is_not_running_is_an_unapplied_change(state):
    state.toggle("core")
    assert _has_unapplied_changes(state)


def _label(state, pkg_id, status="stopped"):
    monkey = pytest.MonkeyPatch()
    monkey.setattr(tui, "get_pkg_status", lambda _p: status)
    try:
        screen = _Screen()
        tui.draw_tui(screen, state, 0, None, None)
    finally:
        monkey.undo()
    name = state.get_by_id(pkg_id).name
    y = next(y for y, _, t, _ in screen.writes if name in t)
    return [(t, a) for r, _, t, a in screen.writes if r == y][-1]


def test_a_ticked_but_stopped_row_shows_a_dim_stopped_label(state):
    _core_off_with_robot(state)
    assert _label(state, "robot_so_arm101") == (" [STOPPED]", _Curses.A_DIM)


def test_an_unticked_stopped_row_shows_no_label(state):
    assert not _label(state, "robot_so_arm101")[0].strip().endswith("]")
