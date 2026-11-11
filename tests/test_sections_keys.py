import pytest

from launcher import tui
from sections_support import (
    KEY_DOWN,
    KEY_LEFT,
    KEY_RESIZE,
    KEY_RIGHT,
    clock,
    draw,
    folded_titles,
    go_to,
    header_row,
    quit,
    run,
    state,
)


@pytest.mark.parametrize("key", [ord(" "), KEY_LEFT])
def test_space_and_left_fold_an_open_header(state, key):
    screen, _ = run(state, go_to(state, "Tools") + [key] + quit())
    assert folded_titles(screen) == ["Tools"]


def test_right_unfolds_a_folded_header(state):
    keys = go_to(state, "Tools") + [KEY_LEFT, KEY_RIGHT] + quit()
    screen, _ = run(state, keys)
    assert folded_titles(screen) == []


def test_space_twice_on_a_header_opens_it_again(state):
    keys = go_to(state, "Tools") + [ord(" "), ord(" ")] + quit()
    screen, _ = run(state, keys)
    assert folded_titles(screen) == []


@pytest.mark.parametrize("key", [ord(" "), KEY_LEFT, KEY_RIGHT])
def test_fold_keys_on_a_header_do_not_toggle_packages(state, key):
    before = {p.id for p in state.packages if p.selected}
    run(state, go_to(state, "Robot") + [key] + quit())
    assert {p.id for p in state.packages if p.selected} == before


def test_enter_on_a_header_still_applies(state, monkeypatch):
    applied = []
    monkeypatch.setattr(tui, "apply_changes", lambda s: applied.append(s))
    run(state, go_to(state, "Tools") + [ord("\n")] + quit())
    assert len(applied) == 1


def test_the_cursor_is_clamped_after_the_screen_shrinks(state):
    _, display = draw(state)
    keys = [KEY_DOWN] * (len(display) - 1) + [KEY_RESIZE] + quit()
    screen, result = run(state, keys, shrink=(20, 120))
    assert result[0] == "ExitWorkspace"
    row = header_row(screen, "Options")
    assert (row, 0, "> ") in [(y, x, t) for y, x, t, _ in screen.writes]


@pytest.mark.parametrize("height", [20, 27])
@pytest.mark.parametrize("key", [ord(" "), KEY_RIGHT])
def test_opening_a_section_with_no_room_warns_and_leaves_it_folded(
    state, clock, height, key
):
    keys = go_to(state, "Tools", height) + [key] + quit()
    screen, _ = run(state, keys, size=(height, 120), clock=clock)
    assert any("Terminal too small to open Tools" in s for s in screen.seen)
    assert "▸ Tools" in [t for _, _, t, _ in screen.writes]


def test_opening_a_section_with_room_shows_no_warning(state, clock):
    keys = go_to(state, "Tools") + [ord(" "), ord(" ")] + quit()
    screen, _ = run(state, keys, clock=clock)
    assert not any("too small" in s for s in screen.seen)
    assert folded_titles(screen) == []


def test_space_opens_a_section_that_was_only_folded_for_lack_of_room(state, clock):
    keys = go_to(state, "Robot", 27) + [KEY_LEFT, KEY_DOWN, KEY_LEFT]
    keys += [KEY_DOWN, KEY_LEFT, ord(" ")] + quit()
    screen, _ = run(state, keys, size=(27, 120), clock=clock)
    assert "Tools" not in folded_titles(screen)
    assert not any("too small" in s for s in screen.seen)


def _toggle_warning_keys(state):
    state.toggle("core")
    _, display = draw(state)
    return [KEY_DOWN] * display.index(state.get_by_id("simulator")) + [ord(" ")]


def test_a_toggle_warning_survives_redraw_ticks_and_expires_after_three_seconds(
    state, clock
):
    keys = _toggle_warning_keys(state)
    start = len(keys) - 1
    keys += [("advance", 1), ("advance", 1), ("advance", 1.5), ("advance", 0)]
    screen, _ = run(state, keys + quit(), clock=clock)
    assert all(
        "One launch mode required" in s for s in screen.seen[start + 1 : start + 4]
    )
    assert "One launch mode" not in screen.seen[start + 5]


def test_the_loop_ticks_while_a_warning_is_showing(state, clock):
    keys = _toggle_warning_keys(state)
    start = len(keys) - 1
    screen, _ = run(state, keys + [("advance", 0)] + quit(), clock=clock)
    assert screen.timeouts[start] == -1
    assert screen.timeouts[start + 1] == tui.REDRAW_INTERVAL_MS
