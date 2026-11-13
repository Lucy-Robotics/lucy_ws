"""Tests for Lucy.py's menu key handling."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Lucy  # noqa: E402


class _StubCurses:
    """Just the surface main_tui touches."""
    KEY_UP, KEY_DOWN = 259, 258
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    COLOR_CYAN = 6

    def __init__(self): self.escdelay = None
    def set_escdelay(self, ms): self.escdelay = ms
    def curs_set(self, _): pass
    def start_color(self): pass
    def use_default_colors(self): pass
    def init_pair(self, *_): pass


class _StubScreen:
    def __init__(self, keys, size=(24, 80)):
        self._keys = list(keys)
        self._size = size
        self.written = []

    def getmaxyx(self): return self._size
    def clear(self): pass
    def refresh(self): pass
    def nodelay(self, _): pass
    def timeout(self, _): pass
    def addstr(self, _y, _x, text, *_): self.written.append(text)
    def getch(self): return self._keys.pop(0)


@pytest.fixture
def stub_curses(monkeypatch):
    stub = _StubCurses()
    monkeypatch.setattr(Lucy, "curses", stub)
    return stub


@pytest.mark.parametrize("key", ["q", "Q", "x", "X"])
def test_quit_keys_leave_the_menu(stub_curses, key):
    assert Lucy.main_tui(_StubScreen([ord(key)])) is None


def test_escape_leaves_the_menu(stub_curses):
    assert Lucy.main_tui(_StubScreen([27])) is None


def test_footer_fits_the_minimum_terminal_width(stub_curses):
    screen = _StubScreen([ord("q")])
    Lucy.main_tui(screen)
    # addstr starts at column 2 and curses errors on overflow.
    assert max(len(line) for line in screen.written) + 2 <= Lucy.MIN_TERM_WIDTH


def test_navigation_keys_still_work(stub_curses):
    """Down then quit: arrows must not be swallowed by the new branch."""
    screen = _StubScreen([_StubCurses.KEY_DOWN, _StubCurses.KEY_UP, ord("q")])
    assert Lucy.main_tui(screen) is None


def test_escape_delay_is_shortened(stub_curses):
    """ncurses defaults to 1000 ms, which makes ESC feel frozen next to q and x."""
    Lucy.main_tui(_StubScreen([ord("q")]))
    assert stub_curses.escdelay == Lucy.ESCAPE_DELAY_MS
    assert 0 < Lucy.ESCAPE_DELAY_MS <= 100


def test_escape_delay_is_optional(monkeypatch):
    """Builds without set_escdelay must still run the menu."""
    stub = _StubCurses()
    monkeypatch.delattr(_StubCurses, "set_escdelay")
    monkeypatch.setattr(Lucy, "curses", stub)
    assert Lucy.main_tui(_StubScreen([ord("q")])) is None


@pytest.mark.parametrize("value, session", [("2", "lucy_ws_2"), ("lucy_ws_0", "lucy_ws_0"), ("03", "lucy_ws_3")])
def test_ws_flag_picks_the_instance(value, session):
    assert Lucy.parse_args(["-ws", value]).ws == session


@pytest.mark.parametrize("value", ["robot", "lucy_ws", "lucy_ws_x", "../x"])
def test_ws_flag_rejects_names_without_a_number(value):
    with pytest.raises(SystemExit):
        Lucy.parse_args(["-ws", value])


def test_ws_flag_is_optional():
    assert Lucy.parse_args([]).ws is None
