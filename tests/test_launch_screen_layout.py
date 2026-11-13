import pytest

from launcher import domain_field, links, sections, tui
from launcher.domain_field import DOMAIN_ROW


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, size):
        self.size = size
        self.rows = []
        self.cols = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.rows = []
        self.cols = []

    def refresh(self):
        pass

    def addstr(self, y, x, text, attr=0):
        self.rows.append((y, text, attr))
        self.cols.append((y, x, text))


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links, sections):
        monkeypatch.setattr(module, "curses", _Curses())
    return isolated_state


def _draw(state, current=0, size=(80, 120)):
    screen = _Screen(size)
    return screen, tui.draw_tui(screen, state, current, None, None)


def _row(screen, needle):
    return next(y for y, text, _ in screen.rows if needle in text)


def _min_height(state):
    return 2 * 5 + 4


def test_visualizer_is_listed_under_tools(state):
    screen, _ = _draw(state)
    assert _row(screen, "Visualizer") > _row(screen, "Tools")


def test_domain_is_the_only_item_of_options_section_below_tools(state):
    screen, _ = _draw(state)
    assert _row(screen, "Tools") < _row(screen, "Options") < _row(screen, "ROS domain")
    assert _row(screen, "ROS domain") == _row(screen, "Options") + 1


def test_domain_row_is_last_display_entry(state):
    _, display = _draw(state)
    assert display[-1] is DOMAIN_ROW
    assert display.count(DOMAIN_ROW) == 1


def _domain_pieces(screen):
    y = _row(screen, "ROS domain")
    return [(t, a) for r, t, a in screen.rows if r == y]


def _pend(state):
    state.get_by_id("core").is_running = True
    state.running_domain_id = state.domain_id + 1


def test_domain_row_reads_counter_once_pieces_are_joined(state):
    screen, _ = _draw(state)
    joined = "".join(t for t, _ in _domain_pieces(screen))
    assert joined == f"  ROS domain ID: < {state.domain_id} >"


@pytest.mark.parametrize("pending", [False, True])
def test_domain_row_ends_with_closing_bracket_when_current(state, pending):
    if pending:
        _pend(state)
    _, display = _draw(state)
    screen, _ = _draw(state, current=len(display) - 1)
    pieces = _domain_pieces(screen)
    assert [t for t, _ in pieces][1:] == [str(state.domain_id), " >"]
    assert pieces[0][0] == "> ROS domain ID: < "


def test_domain_row_is_dim_without_core(state):
    screen, _ = _draw(state)
    pieces = _domain_pieces(screen)
    assert {pieces[0][1], pieces[1][1], pieces[2][1]} == {_Curses.A_DIM}


def test_domain_row_is_normal_with_core(state):
    state.toggle("core")
    screen, _ = _draw(state)
    pieces = _domain_pieces(screen)
    assert {pieces[0][1], pieces[1][1], pieces[2][1]} == {_Curses.A_NORMAL}


def test_domain_number_is_yellow_only_when_restart_is_pending(state):
    _pend(state)
    screen, _ = _draw(state)
    pieces = _domain_pieces(screen)
    assert [a for _, a in pieces] == [
        _Curses.A_DIM,
        _Curses().color_pair(1),
        _Curses.A_DIM,
    ]


def _col(screen, name, mark="["):
    _, x, text = next(c for c in screen.cols if name in c[2])
    return x + text.index(mark)


def test_core_checkbox_is_in_column_six_like_other_items(state):
    screen, _ = _draw(state)
    assert _col(screen, "Core") == _col(screen, "Visualizer") == 6


@pytest.mark.parametrize("name", ["InMoov i2", "Control Panel"])
def test_robot_and_interface_checkboxes_share_column_six(state, name):
    screen, _ = _draw(state)
    assert _col(screen, name) == 6


@pytest.mark.parametrize("name", ["Simulator", "Hardware"])
def test_mode_checkboxes_are_indented_to_column_ten(state, name):
    screen, _ = _draw(state)
    assert _col(screen, name) == 10


@pytest.mark.parametrize("name", ["Visualizer", "rqt GUI"])
def test_tool_checkboxes_share_column_six(state, name):
    screen, _ = _draw(state)
    assert _col(screen, name) == 6


def test_domain_label_starts_in_column_six(state):
    screen, _ = _draw(state)
    assert _col(screen, "ROS domain", "R") == 6


@pytest.mark.parametrize("name", ["Headless", "Micro controllers", "USB servos"])
def test_subitem_checkboxes_are_in_column_fourteen(state, name):
    screen, _ = _draw(state)
    assert _col(screen, name) == 14


def test_stack_header_follows_two_blank_rows_under_the_title(state):
    screen, _ = _draw(state)
    assert _row(screen, "Lucy Launch Screen") == 0
    assert _row(screen, "Stack") == 3
    assert _row(screen, "Core") == 4
    assert not any(y in (1, 2) for y, _, _ in screen.rows)


def test_footer_text(state):
    screen, _ = _draw(state)
    assert any(
        t == "Enter: Apply | Space: Toggle | Q/X/Esc: Stop All & Exit"
        for _, t, _ in screen.rows
    )


def test_one_row_below_minimum_height_draws_too_small_message(state):
    needed = _min_height(state)
    screen, display = _draw(state, size=(needed - 1, 120))
    assert display is None
    assert any(
        t == f"({tui.MIN_TERM_WIDTH}x{needed} required)" for _, t, _ in screen.rows
    )


def test_minimum_height_draws_without_error(state):
    _, display = _draw(state, size=(_min_height(state), 120))
    assert display is not None


def test_minimum_height_of_the_shipped_config_is_fourteen(state):
    assert _min_height(state) == 14
