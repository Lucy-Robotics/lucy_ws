import subprocess
import types

import pytest

from launcher import domain_field, links, sections, tui
from launcher.links import ADD_INTERFACE, ADD_ROBOT, open_link

URL = ADD_ROBOT.url
KEY_UP, KEY_DOWN, KEY_RESIZE = 1001, 1002, 1003


class _CursesError(Exception):
    pass


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    KEY_UP, KEY_DOWN, KEY_RESIZE = KEY_UP, KEY_DOWN, KEY_RESIZE
    KEY_LEFT, KEY_RIGHT = 1004, 1005
    error = _CursesError

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, keys=(), size=(80, 120)):
        self.size = size
        self.keys = list(keys)
        self.writes = []
        self.frames = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        if self.writes:
            self.frames.append(self.writes)
        self.writes = []

    def refresh(self):
        pass

    def nodelay(self, _flag):
        pass

    def timeout(self, _ms):
        pass

    def getch(self):
        assert self.keys, "scripted keys exhausted"
        return self.keys.pop(0)

    def addstr(self, y, x, text, attr=0):
        self.writes.append((y, x, text, attr))


class _Poller:
    def take(self):
        return None

    def set_interval(self, _seconds):
        pass

    def request_refresh(self):
        self.refreshed = True


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links, sections):
        monkeypatch.setattr(module, "curses", _Curses())
    return isolated_state


@pytest.fixture
def popen(monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: calls.append((a, k)) or None
    )
    monkeypatch.setattr(links.sys, "platform", "linux")
    monkeypatch.setattr(links.os, "name", "posix")
    monkeypatch.setattr(links.shutil, "which", lambda _n: "/usr/bin/xdg-open")
    for var in ("DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(var, raising=False)
    return calls


def _draw(state, current=0):
    screen = _Screen()
    return screen, tui.draw_tui(screen, state, current, None, None)


def _link_writes(screen, link):
    y = next(y for y, _, t, _ in screen.writes if link.name in t)
    return [w for w in screen.writes if w[0] == y]


def _section_items(screen, state, display, link):
    return display[display.index(link) - 1], display[display.index(link) + 1]


def test_add_robot_row_is_last_of_the_robot_section(state):
    _, display = _draw(state)
    before, after = _section_items(None, state, display, ADD_ROBOT)
    assert before.type == "modifier" and before.requires_pkg
    assert after == sections.SectionRow("Control Interfaces", 3)


def test_add_interface_row_is_last_of_the_interfaces_section(state):
    _, display = _draw(state)
    before, after = _section_items(None, state, display, ADD_INTERFACE)
    assert before.type == "interface"
    assert after == sections.SectionRow("Tools", 3)


@pytest.mark.parametrize("link", [ADD_ROBOT, ADD_INTERFACE])
def test_add_yours_starts_in_the_column_of_package_names(state, link):
    screen, _ = _draw(state)
    prefix, label = _link_writes(screen, link)[:2]
    assert prefix[1] + len(prefix[2]) == label[1] == 6
    assert label[2].index("Add yours") == 4


def test_add_yours_is_drawn_italic(state, monkeypatch):
    monkeypatch.setattr(_Curses, "A_ITALIC", 64, raising=False)
    screen, _ = _draw(state)
    assert _link_writes(screen, ADD_ROBOT)[1][3] == 64


def test_add_yours_is_plain_when_curses_has_no_italic(state):
    screen, _ = _draw(state)
    assert _link_writes(screen, ADD_ROBOT)[1][3] == _Curses.A_NORMAL


def test_the_cursor_prefix_carries_no_attribute(state):
    screen, _ = _draw(state)
    assert _link_writes(screen, ADD_ROBOT)[0][3] == 0


@pytest.mark.parametrize("current", [True, False])
def test_link_row_starts_with_the_cursor_prefix(state, current):
    _, display = _draw(state)
    screen, _ = _draw(state, display.index(ADD_ROBOT) if current else 0)
    assert _link_writes(screen, ADD_ROBOT)[0][2] == ("> " if current else "  ")


def test_open_link_without_a_desktop_says_where_to_open(popen):
    assert open_link(ADD_ROBOT) == f"Open in a browser: {URL}"
    assert popen == []


def test_open_link_without_xdg_open_says_where_to_open(popen, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(links.shutil, "which", lambda _n: None)
    assert open_link(ADD_ROBOT) == f"Open in a browser: {URL}"


@pytest.mark.parametrize("var", ["DISPLAY", "WAYLAND_DISPLAY"])
def test_open_link_with_a_desktop_runs_xdg_open_detached_and_silenced(
    popen, monkeypatch, var
):
    monkeypatch.setenv(var, "x")
    assert open_link(ADD_ROBOT) == f"Opened {URL}"
    (args,), kwargs = popen[0]
    assert args == ["xdg-open", URL]
    assert kwargs == {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }


def test_open_link_falls_back_when_the_opener_fails(popen, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")

    def boom(*_a, **_k):
        raise OSError

    monkeypatch.setattr(subprocess, "Popen", boom)
    assert open_link(ADD_ROBOT) == f"Open in a browser: {URL}"


def test_open_link_on_macos_uses_open(popen, monkeypatch):
    monkeypatch.setattr(links.sys, "platform", "darwin")
    assert open_link(ADD_ROBOT) == f"Opened {URL}"
    assert popen[0][0][0] == ["open", URL]


def _run(state, monkeypatch, presses, keys):
    applied = []
    opened = []
    monkeypatch.setattr(tui, "apply_changes", lambda s: applied.append(s))
    monkeypatch.setattr(tui, "open_link", lambda row: opened.append(row) or "OPENED")
    monkeypatch.setattr(tui, "write_stack_status", lambda _s: None)
    monkeypatch.setattr(tui, "take_robot_request", lambda _s: None)
    selected = {p.id for p in state.packages if p.selected}
    screen = _Screen([KEY_DOWN] * presses + keys + [ord("x"), ord("y")])
    result = tui._event_loop(screen, state, _Poller())
    return screen, applied, opened, selected, result


@pytest.mark.parametrize("key", [ord(" "), ord("\n")])
def test_space_or_enter_on_a_link_row_opens_it_without_toggling_or_applying(
    state, monkeypatch, key
):
    _, display = _draw(state)
    screen, applied, opened, selected, result = _run(
        state, monkeypatch, display.index(ADD_ROBOT), [key]
    )
    assert opened == [ADD_ROBOT]
    assert applied == []
    assert {p.id for p in state.packages if p.selected} == selected
    assert result[0] == "ExitWorkspace"
    assert any(t == "OPENED" for frame in screen.frames for _, _, t, _ in frame)


def test_enter_off_a_link_row_still_applies(state, monkeypatch):
    _, applied, opened, _, _ = _run(state, monkeypatch, 0, [ord("\n")])
    assert opened == []
    assert len(applied) == 1


def test_a_long_status_message_is_cut_to_fit_the_width(state):
    screen = _Screen(size=(80, 100))
    tui.draw_tui(screen, state, 0, None, "x" * 500)
    text = next(t for y, _, t, _ in screen.writes if y == 78 and t.startswith("x"))
    assert len(text) + 2 <= 100 - 1
