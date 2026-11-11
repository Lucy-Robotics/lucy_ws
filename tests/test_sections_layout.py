import pytest

from launcher import domain_field
from launcher.sections import SectionRow
from sections_support import (
    Curses,
    draw,
    folded_titles,
    header_row,
    row_text,
    state,
)

TITLES = ["Robot", "Control Interfaces", "Tools", "Options"]


def test_each_titled_section_has_a_header_before_its_items(state):
    _, display = draw(state)
    assert [s.title for s in display if isinstance(s, SectionRow)] == TITLES
    after_tools = display[display.index(SectionRow("Tools", 3)) + 1]
    assert after_tools.type == "tool" or after_tools.section == "tools"
    assert display[-1] is domain_field.DOMAIN_ROW


def test_the_core_block_has_no_header(state):
    _, display = draw(state)
    assert display[0].type == "core"


def test_an_open_section_shows_a_down_chevron_in_column_two(state):
    screen, _ = draw(state)
    row = header_row(screen, "Tools")
    assert (row, 2, "▾ Tools") in [(y, x, t) for y, x, t, _ in screen.writes]


def test_a_folded_section_shows_a_right_chevron_and_drops_its_items(state):
    screen, display = draw(state, folded={"Tools"})
    assert "▸ Tools" in [t for _, _, t, _ in screen.writes]
    assert not any("rqt GUI" in t for _, _, t, _ in screen.writes)
    assert display[display.index(SectionRow("Tools", 3)) + 1] is not None
    assert all(getattr(p, "name", "") != "rqt GUI" for p in display)


def test_the_header_is_bold_in_its_section_colour(state):
    screen, _ = draw(state)
    attrs = {t[2:]: a for _, x, t, a in screen.writes if x == 2 and t[:1] in "▾▸"}
    assert attrs["Robot"] == Curses.A_BOLD | (1 << 8)
    assert attrs["Tools"] == Curses.A_BOLD | (3 << 8)


def test_the_folded_robot_summary_lists_the_ticked_robots(state):
    state.get_by_id("robot_so_arm101").selected = True
    ticked = ", ".join(
        p.name
        for p in state.packages
        if p.type == "modifier" and p.requires_pkg and p.selected
    )
    screen, _ = draw(state, folded={"Robot"})
    assert ticked
    assert row_text(screen, header_row(screen, "Robot")).endswith(f"  {ticked}")


def test_the_folded_robot_summary_is_dim(state):
    state.get_by_id("robot_so_arm101").selected = True
    screen, _ = draw(state, folded={"Robot"})
    row = header_row(screen, "Robot")
    assert [a for r, _, _, a in screen.writes if r == row][-1] == Curses.A_DIM


def test_the_folded_options_summary_is_the_ros_domain(state):
    screen, _ = draw(state, folded={"Options"})
    text = row_text(screen, header_row(screen, "Options"))
    assert text.endswith(f"  ROS domain {state.domain_id}")


def test_an_open_section_shows_no_summary(state):
    screen, _ = draw(state)
    assert row_text(screen, header_row(screen, "Options")).endswith("Options")


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
    screen, display = draw(state, height=height)
    assert display is not None
    assert sorted(folded_titles(screen)) == sorted(folded)


def test_one_row_below_every_section_folded_is_too_small(state):
    screen, display = draw(state, height=19)
    assert display is None
    assert any(t == "(40x20 required)" for _, _, t, _ in screen.writes)


def test_user_folded_sections_stay_folded_when_the_screen_is_tall(state):
    screen, _ = draw(state, folded={"Robot"})
    assert folded_titles(screen) == ["Robot"]


@pytest.mark.parametrize("height", [80, 20])
def test_headers_open_or_folded_never_overflow_forty_columns(state, height):
    for pkg in state.packages:
        pkg.selected = True
    state.running_domain_id = state.domain_id + 1
    screen, display = draw(state, height=height, width=40)
    assert display is not None


def test_every_section_folded_with_everything_ticked_fits_forty_columns(state):
    for pkg in state.packages:
        pkg.selected = True
    _, display = draw(state, height=80, width=40, folded=set(TITLES))
    assert display is not None
