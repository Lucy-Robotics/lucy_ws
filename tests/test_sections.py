import pytest

from launcher import domain_field, links, sections, tui
from launcher.sections import SectionRow

KEY_UP, KEY_DOWN, KEY_RESIZE, KEY_LEFT, KEY_RIGHT = 1001, 1002, 1003, 1004, 1005
TITLES = ["Robot", "Control Interfaces", "Tools", "Options"]


class _CursesError(Exception):
    pass


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    KEY_UP, KEY_DOWN, KEY_RESIZE = KEY_UP, KEY_DOWN, KEY_RESIZE
    KEY_LEFT, KEY_RIGHT = KEY_LEFT, KEY_RIGHT
    error = _CursesError

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, size=(80, 120), keys=(), shrink=None):
        self.size = size
        self.keys = list(keys)
        self.shrink = shrink
        self.writes = []

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.writes = []

    def refresh(self):
        pass

    def nodelay(self, _flag):
        pass

    def timeout(self, _ms):
        pass

    def getch(self):
        assert self.keys, "scripted keys exhausted"
        key = self.keys.pop(0)
        if key == KEY_RESIZE and self.shrink:
            self.size = self.shrink
        return key

    def addstr(self, y, x, text, attr=0):
        assert x + len(text) <= self.size[1], f"row {y} overflows: {text!r}"
        self.writes.append((y, x, text, attr))


class _Poller:
    def take(self):
        return None

    def set_interval(self, _seconds):
        pass

    def request_refresh(self):
        pass


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links, sections):
        monkeypatch.setattr(module, "curses", _Curses())
    monkeypatch.setattr(tui, "write_stack_status", lambda _s: None)
    monkeypatch.setattr(tui, "take_robot_request", lambda _s: None)
    return isolated_state


def _draw(state, height=80, width=120, current=0, folded=frozenset()):
    screen = _Screen((height, width))
    display = tui.draw_tui(screen, state, current, None, None, folded=folded)
    return screen, display


def _header_row(screen, title):
    return next(y for y, x, t, _ in screen.writes if x == 2 and t[2:].startswith(title))


def _row_text(screen, y):
    return "".join(t for r, _, t, _ in screen.writes if r == y)


def _folded_titles(screen):
    return [t[2:] for _, x, t, _ in screen.writes if x == 2 and t.startswith("▸ ")]


def _run(state, keys, **kwargs):
    screen = _Screen(keys=keys, **kwargs)
    result = tui._event_loop(screen, state, _Poller())
    return screen, result


def _quit():
    return [ord("x"), ord("y")]


def _go_to(state, title):
    _, display = _draw(state)
    return [KEY_DOWN] * display.index(
        next(s for s in display if isinstance(s, SectionRow) and s.title == title)
    )


def test_each_titled_section_has_a_header_before_its_items(state):
    _, display = _draw(state)
    assert [s.title for s in display if isinstance(s, SectionRow)] == TITLES
    after_tools = display[display.index(SectionRow("Tools", 3)) + 1]
    assert after_tools.type == "tool" or after_tools.section == "tools"
    assert display[-1] is domain_field.DOMAIN_ROW


def test_the_core_block_has_no_header(state):
    _, display = _draw(state)
    assert display[0].type == "core"


def test_an_open_section_shows_a_down_chevron_in_column_two(state):
    screen, _ = _draw(state)
    row = _header_row(screen, "Tools")
    assert (row, 2, "▾ Tools") in [(y, x, t) for y, x, t, _ in screen.writes]


def test_a_folded_section_shows_a_right_chevron_and_drops_its_items(state):
    screen, display = _draw(state, folded={"Tools"})
    assert "▸ Tools" in [t for _, _, t, _ in screen.writes]
    assert not any("rqt GUI" in t for _, _, t, _ in screen.writes)
    assert display[display.index(SectionRow("Tools", 3)) + 1] is not None
    assert all(getattr(p, "name", "") != "rqt GUI" for p in display)


def test_the_header_is_bold_in_its_section_colour(state):
    screen, _ = _draw(state)
    attrs = {t[2:]: a for _, x, t, a in screen.writes if x == 2 and t[:1] in "▾▸"}
    assert attrs["Robot"] == _Curses.A_BOLD | (1 << 8)
    assert attrs["Tools"] == _Curses.A_BOLD | (3 << 8)


@pytest.mark.parametrize("key", [ord(" "), KEY_LEFT])
def test_space_and_left_fold_an_open_header(state, key):
    screen, _ = _run(state, _go_to(state, "Tools") + [key] + _quit())
    assert _folded_titles(screen) == ["Tools"]


def test_right_unfolds_a_folded_header(state):
    keys = _go_to(state, "Tools") + [KEY_LEFT, KEY_RIGHT] + _quit()
    screen, _ = _run(state, keys)
    assert _folded_titles(screen) == []


def test_space_twice_on_a_header_opens_it_again(state):
    keys = _go_to(state, "Tools") + [ord(" "), ord(" ")] + _quit()
    screen, _ = _run(state, keys)
    assert _folded_titles(screen) == []


@pytest.mark.parametrize("key", [ord(" "), KEY_LEFT, KEY_RIGHT])
def test_fold_keys_on_a_header_do_not_toggle_packages(state, key):
    before = {p.id for p in state.packages if p.selected}
    _run(state, _go_to(state, "Robot") + [key] + _quit())
    assert {p.id for p in state.packages if p.selected} == before


def test_enter_on_a_header_still_applies(state, monkeypatch):
    applied = []
    monkeypatch.setattr(tui, "apply_changes", lambda s: applied.append(s))
    _run(state, _go_to(state, "Tools") + [ord("\n")] + _quit())
    assert len(applied) == 1


def test_the_folded_robot_summary_lists_the_ticked_robots(state):
    state.get_by_id("robot_so_arm101").selected = True
    ticked = ", ".join(
        p.name
        for p in state.packages
        if p.type == "modifier" and p.requires_pkg and p.selected
    )
    screen, _ = _draw(state, folded={"Robot"})
    assert ticked
    assert _row_text(screen, _header_row(screen, "Robot")).endswith(f"  {ticked}")


def test_the_folded_robot_summary_is_dim(state):
    state.get_by_id("robot_so_arm101").selected = True
    screen, _ = _draw(state, folded={"Robot"})
    row = _header_row(screen, "Robot")
    assert [a for r, _, _, a in screen.writes if r == row][-1] == _Curses.A_DIM


def test_the_folded_options_summary_is_the_ros_domain(state):
    screen, _ = _draw(state, folded={"Options"})
    text = _row_text(screen, _header_row(screen, "Options"))
    assert text.endswith(f"  ROS domain {state.domain_id}")


def test_an_open_section_shows_no_summary(state):
    screen, _ = _draw(state)
    assert _row_text(screen, _header_row(screen, "Options")).endswith("Options")


@pytest.mark.parametrize(
    "height, folded",
    [
        (31, []),
        (27, ["Tools", "Options"]),
        (24, ["Control Interfaces", "Tools", "Options"]),
        (20, TITLES),
    ],
)
def test_sections_fold_from_the_bottom_up_as_the_screen_shrinks(state, height, folded):
    screen, display = _draw(state, height=height)
    assert display is not None
    assert sorted(_folded_titles(screen)) == sorted(folded)


def test_one_row_below_every_section_folded_is_too_small(state):
    screen, display = _draw(state, height=19)
    assert display is None
    assert any(t == "(40x20 required)" for _, _, t, _ in screen.writes)


def test_user_folded_sections_stay_folded_when_the_screen_is_tall(state):
    screen, _ = _draw(state, folded={"Robot"})
    assert _folded_titles(screen) == ["Robot"]


def test_the_cursor_is_clamped_after_the_screen_shrinks(state):
    _, display = _draw(state)
    keys = [KEY_DOWN] * (len(display) - 1) + [KEY_RESIZE] + _quit()
    screen, result = _run(state, keys, shrink=(20, 120))
    assert result[0] == "ExitWorkspace"
    row = _header_row(screen, "Options")
    assert (row, 0, "> ") in [(y, x, t) for y, x, t, _ in screen.writes]


@pytest.mark.parametrize("height", [80, 20])
def test_headers_open_or_folded_never_overflow_forty_columns(state, height):
    for pkg in state.packages:
        pkg.selected = True
    state.running_domain_id = state.domain_id + 1
    screen, display = _draw(state, height=height, width=40)
    assert display is not None


def test_every_section_folded_with_everything_ticked_fits_forty_columns(state):
    for pkg in state.packages:
        pkg.selected = True
    _, display = _draw(state, height=80, width=40, folded=set(TITLES))
    assert display is not None
