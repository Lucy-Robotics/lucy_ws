import pytest

from launcher import domain_field, tui
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

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.rows = []

    def refresh(self):
        pass

    def addstr(self, y, x, text, attr=0):
        self.rows.append((y, text, attr))


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field):
        monkeypatch.setattr(module, "curses", _Curses())
    return isolated_state


def _draw(state, current=0, size=(80, 120)):
    screen = _Screen(size)
    return screen, tui.draw_tui(screen, state, current, None, None)


def _row(screen, needle):
    return next(y for y, text, _ in screen.rows if needle in text)


def _min_height(state):
    pkgs = state.packages
    robots = [p for p in pkgs if p.type == "modifier" and p.requires_pkg]
    primary = [p for p in pkgs if p.type == "core"] + [
        p
        for p in pkgs
        if p.type == "modifier" and not p.requires_pkg and p.section != "tools"
    ]
    interfaces = [p for p in pkgs if p.type == "interface"]
    tools = [p for p in pkgs if p.type == "tool" or p.section == "tools"]
    sections = [primary, interfaces, tools, [DOMAIN_ROW]] + ([robots] if robots else [])
    return max(tui.MIN_TERM_HEIGHT, sum(len(s) + 2 for s in sections) + 2)


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


def test_domain_row_is_drawn_with_counter(state):
    screen, _ = _draw(state)
    assert any(
        text == f"  ROS domain ID: < {state.domain_id} >" for _, text, _ in screen.rows
    )


def test_domain_row_is_dim_without_core(state):
    screen, _ = _draw(state)
    assert next(a for _, t, a in screen.rows if "ROS domain" in t) == _Curses.A_DIM


def test_domain_row_is_normal_with_core(state):
    state.toggle("core")
    screen, _ = _draw(state)
    assert next(a for _, t, a in screen.rows if "ROS domain" in t) == _Curses.A_NORMAL


def test_domain_row_hint_shows_when_current(state):
    _, display = _draw(state)
    screen, _ = _draw(state, current=len(display) - 1)
    assert any("Left/Right to change" in t for _, t, _ in screen.rows)


def test_domain_row_hint_hidden_when_not_current(state):
    screen, _ = _draw(state)
    assert not any("Left/Right" in t for _, t, _ in screen.rows)


def test_restart_hint_shows_running_domain(state):
    state.get_by_id("core").is_running = True
    state.running_domain_id = state.domain_id + 1
    screen, _ = _draw(state)
    assert any(
        f"core runs on {state.running_domain_id}, Enter restarts it" in t
        for _, t, _ in screen.rows
    )


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
