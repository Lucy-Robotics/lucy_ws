import curses as real_curses

import pytest

from launcher import domain_field
from launcher.domain_field import domain_step, draw_domain_row


class _Curses:
    A_DIM, A_NORMAL = 2, 0
    KEY_LEFT, KEY_RIGHT = real_curses.KEY_LEFT, real_curses.KEY_RIGHT
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, width=120):
        self.width = width
        self.cells = []

    def getmaxyx(self):
        return (40, self.width)

    def addstr(self, y, x, text, attr=0):
        self.cells.append((text, attr))


@pytest.fixture
def state(isolated_state, monkeypatch):
    monkeypatch.setattr(domain_field, "curses", _Curses())
    return isolated_state


def _draw(state, current=False, width=120):
    screen = _Screen(width)
    draw_domain_row(screen, 3, 4, state, current)
    return screen.cells


@pytest.mark.parametrize("key", [real_curses.KEY_RIGHT, ord("+"), ord("=")])
def test_increase_keys_step_up(state, key):
    assert domain_step(key) == 1


@pytest.mark.parametrize("key", [real_curses.KEY_LEFT, ord("-")])
def test_decrease_keys_step_down(state, key):
    assert domain_step(key) == -1


@pytest.mark.parametrize("key", [ord("d"), ord("\n"), ord(" "), real_curses.KEY_UP])
def test_other_keys_do_not_step(state, key):
    assert domain_step(key) == 0


def test_row_shows_domain_id_counter(state):
    assert _draw(state)[0][0] == f"  ROS domain ID: < {state.domain_id} >"


def test_current_row_is_marked_with_cursor(state):
    assert _draw(state, current=True)[0][0].startswith("> ROS domain ID")


def test_row_is_dim_when_core_is_not_selected(state):
    assert _draw(state)[0][1] == _Curses.A_DIM


def test_row_is_normal_when_core_is_selected(state):
    state.toggle("core")
    assert _draw(state)[0][1] == _Curses.A_NORMAL


def test_current_row_hints_left_right(state):
    assert _draw(state, current=True)[1] == (" Left/Right to change", _Curses.A_DIM)


def test_other_rows_have_no_hint(state):
    assert len(_draw(state)) == 1


def test_pending_restart_hint_names_running_domain_in_color(state):
    state.get_by_id("core").is_running = True
    state.running_domain_id = state.domain_id + 1
    hint = _draw(state)[1]
    assert hint == (
        f" core runs on {state.running_domain_id}, Enter restarts it",
        _Curses().color_pair(1),
    )


def test_pending_restart_hint_replaces_change_hint_on_current_row(state):
    state.get_by_id("core").is_running = True
    state.running_domain_id = state.domain_id + 1
    assert "Enter restarts it" in _draw(state, current=True)[1][0]


def test_hint_is_truncated_to_screen_width(state):
    cells = _draw(state, current=True, width=40)
    assert len(cells[0][0]) + 4 + len(cells[1][0]) <= 40 - 1
