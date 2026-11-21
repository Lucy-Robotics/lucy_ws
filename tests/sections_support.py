import types

import pytest

from launcher import domain_field, links, sections, tui
from launcher.sections import SectionRow

KEY_UP, KEY_DOWN, KEY_RESIZE, KEY_LEFT, KEY_RIGHT = 1001, 1002, 1003, 1004, 1005
TITLES = ["Robot", "Control Interfaces", "Tools", "Options"]


class CursesError(Exception):
    pass


class Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    KEY_UP, KEY_DOWN, KEY_RESIZE = KEY_UP, KEY_DOWN, KEY_RESIZE
    KEY_LEFT, KEY_RIGHT = KEY_LEFT, KEY_RIGHT
    error = CursesError

    def color_pair(self, n):
        return n << 8


class Screen:
    def __init__(self, size=(80, 120), keys=(), shrink=None, clock=None):
        self.size = size
        self.clock = clock
        self.seen = []
        self.timeouts = []
        self.keys = list(keys)
        self.resizes = [shrink] if isinstance(shrink, tuple) else list(shrink or [])
        self.writes = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.writes = []

    def refresh(self):
        pass

    def nodelay(self, _flag):
        pass

    def timeout(self, ms):
        self.timeouts.append(ms)

    def getch(self):
        assert self.keys, "scripted keys exhausted"
        self.seen.append(self.bottom())
        key = self.keys.pop(0)
        if isinstance(key, tuple):
            self.clock[0] += key[1]
            return -1
        if key == KEY_RESIZE and self.resizes:
            self.size = self.resizes.pop(0)
        return key

    def bottom(self):
        return "".join(t for y, _, t, _ in self.writes if y == self.size[0] - 2)

    def addstr(self, y, x, text, attr=0):
        assert x + len(text) <= self.size[1], f"row {y} overflows: {text!r}"
        self.writes.append((y, x, text, attr))


class Poller:
    def take(self):
        return None

    def set_interval(self, _seconds):
        pass

    def request_refresh(self):
        pass


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links, sections):
        monkeypatch.setattr(module, "curses", Curses())
    monkeypatch.setattr(tui, "write_stack_status", lambda _s: None)
    monkeypatch.setattr(tui, "take_robot_request", lambda _s: None)
    return isolated_state


def draw(state, height=80, width=120, current=0, folded=frozenset()):
    screen = Screen((height, width))
    display = tui.draw_tui(screen, state, current, None, None, folded=folded)
    return screen, display


def header_row(screen, title):
    return next(y for y, x, t, _ in screen.writes if x == 2 and t[2:].startswith(title))


def row_text(screen, y):
    return "".join(t for r, _, t, _ in screen.writes if r == y)


def folded_titles(screen):
    return [t[2:] for _, x, t, _ in screen.writes if x == 2 and t.startswith("▸ ")]


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    fake = types.SimpleNamespace(time=lambda: now[0], sleep=lambda _s: None)
    monkeypatch.setattr(tui, "time", fake)
    return now


def run(state, keys, **kwargs):
    screen = Screen(keys=keys, **kwargs)
    result = tui._event_loop(screen, state, Poller())
    return screen, result


def quit():
    return [ord("x"), ord("y")]


def go_to(state, title, height=80):
    _, display = draw(state, height=height)
    return [KEY_DOWN] * display.index(
        next(s for s in display if isinstance(s, SectionRow) and s.title == title)
    )
