import itertools

import pytest

from launcher import domain_field, links, sections, tui

WIDTH = 40
FOOTER_WIDTH = 58
STATUSES = ["loading", "crashed", "stopping", "running", "stopped"]


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, width, height=40):
        self.size = (height, width)
        self.writes = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.writes = []

    def refresh(self):
        pass

    def addstr(self, y, x, text, attr=0):
        assert x + len(text) <= self.size[1], f"row {y} overflows: {text!r} at {x}"
        self.writes.append((y, x, text, attr))


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links, sections):
        monkeypatch.setattr(module, "curses", _Curses())
    return isolated_state


def _longest_stage(state):
    stages = state.get_by_id("core").readiness_stages
    index, (label, _) = max(enumerate(stages, 1), key=lambda s: len(s[1][0]))
    return {"index": index, "total": len(stages), "label": label}


def _stress(state, monkeypatch):
    cycle = itertools.cycle(STATUSES)
    monkeypatch.setattr(tui, "get_pkg_status", lambda _p: next(cycle))
    monkeypatch.setattr(tui, "_status_url", lambda _p: "http://localhost:5173/panel")
    monkeypatch.setattr(tui, "_nav_hint", lambda _p: "(tmux ctrl-b 1)")
    stage = _longest_stage(state)
    for pkg in state.packages:
        pkg.stage = stage
    now = links.time.monotonic()
    monkeypatch.setattr(links, "_results", {links.ADD_ROBOT: (True, now)})
    state.get_by_id("core").is_running = True
    state.running_domain_id = state.domain_id + 1


def _draw(state, width, **kwargs):
    screen = _Screen(width)
    result = tui.draw_tui(
        screen,
        state,
        0,
        kwargs.get("error"),
        kwargs.get("status"),
        kwargs.get("unapplied", False),
    )
    return screen, result


def _row_text(screen, y):
    return "".join(t for r, _, t, _ in screen.writes if r == y)


def test_every_row_fits_at_the_minimum_width(state, monkeypatch):
    _stress(state, monkeypatch)
    _, display = _draw(state, WIDTH)
    assert display is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"error": "e" * 200},
        {"status": "s" * 200},
        {"unapplied": True},
    ],
)
def test_bottom_messages_fit_at_the_minimum_width(state, monkeypatch, kwargs):
    _stress(state, monkeypatch)
    _, display = _draw(state, WIDTH, **kwargs)
    assert display is not None


def test_a_long_name_is_cut_and_keeps_the_running_label_whole(monkeypatch):
    monkeypatch.setattr(tui, "curses", _Curses())
    screen = _Screen(WIDTH)
    tui._draw_pkg_row(screen, 3, 4, "> ", "    ", "[x]", "N" * 60, 0, "running")
    text = "".join(t for _, _, t, _ in screen.writes)
    assert text.endswith("... [RUNNING]")
    assert len(text) + 4 <= WIDTH - 1


@pytest.mark.parametrize("width", [40, FOOTER_WIDTH - 1])
def test_the_short_footer_is_used_when_the_full_one_does_not_fit(state, width):
    screen, _ = _draw(state, width)
    assert _row_text(screen, 39) == tui.SHORT_FOOTER


@pytest.mark.parametrize("width", [FOOTER_WIDTH, 120])
def test_the_full_footer_is_used_once_it_fits(state, width):
    screen, _ = _draw(state, width)
    assert _row_text(screen, 39) == tui.FOOTER


def test_a_long_warning_is_cut_to_fit(state):
    screen, _ = _draw(state, WIDTH, error="w" * 200)
    text = _row_text(screen, 38)
    assert text.startswith("Warning: ") and text.endswith("...")
    assert len(text) + 2 <= WIDTH - 1


def test_the_unapplied_line_is_cut_to_fit(state):
    screen, _ = _draw(state, WIDTH, unapplied=True)
    text = _row_text(screen, 38)
    assert text.startswith("Unapplied") and len(text) + 2 <= WIDTH - 1


def test_one_column_below_the_minimum_draws_the_too_small_message(state):
    screen, display = _draw(state, WIDTH - 1)
    assert display is None
    assert any(t.startswith("(40x") for _, _, t, _ in screen.writes)


def test_the_full_footer_threshold_is_its_length_plus_three_columns():
    assert len(tui.FOOTER) + 3 == FOOTER_WIDTH
