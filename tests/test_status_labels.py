import pytest

from launcher import domain_field, links, sections, tui


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
    return isolated_state


def _statuses(monkeypatch, **by_id):
    monkeypatch.setattr(tui, "get_pkg_status", lambda p: by_id.get(p.id, "stopped"))


def _row(state, pkg_id, current=0):
    screen = _Screen()
    tui.draw_tui(screen, state, current, None, None)
    name = state.get_by_id(pkg_id).name
    y = next(y for y, _, t, _ in screen.writes if name in t)
    return [(t, a) for r, _, t, a in screen.writes if r == y]


def _text(pieces):
    return "".join(t for t, _ in pieces)


def test_a_stopped_non_core_row_ends_right_after_its_name(state, monkeypatch):
    _statuses(monkeypatch)
    assert _text(_row(state, "rqt")).endswith("rqt GUI")


@pytest.mark.parametrize("selected", [True, False])
def test_a_stopped_core_row_keeps_its_stopped_label(state, monkeypatch, selected):
    _statuses(monkeypatch)
    state.get_by_id("core").selected = selected
    box = "[x]" if selected else "[ ]"
    assert _text(_row(state, "core")) == f"> {box} Core [STOPPED]"


def test_the_stopped_label_of_core_is_dim(state, monkeypatch):
    _statuses(monkeypatch)
    assert _row(state, "core")[-1] == (" [STOPPED]", _Curses.A_DIM)


def test_a_running_non_core_row_still_shows_running(state, monkeypatch):
    _statuses(monkeypatch, rqt="running")
    assert _text(_row(state, "rqt")).startswith("  [ ] rqt GUI [RUNNING]")


def test_a_crashed_non_core_row_still_shows_crashed(state, monkeypatch):
    _statuses(monkeypatch, rqt="crashed")
    assert _text(_row(state, "rqt")) == "  [ ] rqt GUI [CRASHED]"
