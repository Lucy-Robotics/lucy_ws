import pytest

from launcher import domain_field
from launcher.domain_field import domain_step, draw_domain_row


class _Curses:
    A_DIM, A_NORMAL = 2, 0
    KEY_UP, KEY_LEFT, KEY_RIGHT = 259, 260, 261
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
        self.cells.append((x, text, attr))


@pytest.fixture
def state(isolated_state, monkeypatch):
    monkeypatch.setattr(domain_field, "curses", _Curses())
    return isolated_state


def _draw(state, current=False, width=120):
    screen = _Screen(width)
    draw_domain_row(screen, 3, 4, state, current)
    return sorted(screen.cells)


def _pend(state):
    state.get_by_id("core").is_running = True
    state.running_domain_id = state.domain_id + 1


@pytest.mark.parametrize("key", [_Curses.KEY_RIGHT, ord("+"), ord("=")])
def test_increase_keys_step_up(state, key):
    assert domain_step(key) == 1


@pytest.mark.parametrize("key", [_Curses.KEY_LEFT, ord("-")])
def test_decrease_keys_step_down(state, key):
    assert domain_step(key) == -1


@pytest.mark.parametrize("key", [ord("d"), ord("\n"), ord(" "), _Curses.KEY_UP])
def test_other_keys_do_not_step(state, key):
    assert domain_step(key) == 0


def test_row_reads_domain_id_counter_once_pieces_are_joined(state):
    joined = "".join(text for _, text, _ in _draw(state))
    assert joined == f"  ROS domain ID: < {state.domain_id} >"


def test_current_row_is_marked_with_cursor(state):
    assert _draw(state, current=True)[0][1].startswith("> ROS domain ID")


@pytest.mark.parametrize("current", [False, True])
@pytest.mark.parametrize("pending", [False, True])
def test_nothing_is_drawn_after_closing_bracket(state, current, pending):
    if pending:
        _pend(state)
    assert _draw(state, current=current)[-1][1] == " >"


@pytest.mark.parametrize("pending", [False, True])
def test_row_is_label_number_and_closing_bracket(state, pending):
    if pending:
        _pend(state)
    assert [t for _, t, _ in _draw(state)][1:] == [str(state.domain_id), " >"]


def test_label_and_brackets_are_dim_without_core(state):
    cells = _draw(state)
    assert [cells[0][2], cells[2][2]] == [_Curses.A_DIM] * 2


def test_label_and_brackets_are_normal_with_core(state):
    state.toggle("core")
    cells = _draw(state)
    assert [cells[0][2], cells[2][2]] == [_Curses.A_NORMAL] * 2


def test_number_is_dim_without_core_when_nothing_is_pending(state):
    assert _draw(state)[1][2] == _Curses.A_DIM


def test_number_is_normal_with_core_when_nothing_is_pending(state):
    state.toggle("core")
    assert _draw(state)[1][2] == _Curses.A_NORMAL


def test_number_is_yellow_when_restart_is_pending(state):
    _pend(state)
    assert _draw(state)[1][2] == _Curses().color_pair(1)


def test_label_and_brackets_keep_row_attribute_when_restart_is_pending(state):
    _pend(state)
    cells = _draw(state)
    assert [cells[0][2], cells[2][2]] == [_Curses.A_DIM] * 2
