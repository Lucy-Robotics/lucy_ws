from collections import namedtuple

try:
    import curses
except ImportError:
    curses = None

from .domain_field import DOMAIN_ROW

SectionRow = namedtuple("SectionRow", "title color")


def fold_change(key, folded):
    if key == ord(" "):
        return not folded
    if key == curses.KEY_LEFT:
        return True
    if key == curses.KEY_RIGHT:
        return False
    return None


def rows_needed(titled, folded):
    shown = sum(
        0 if section.title in folded else len(items) for section, items in titled
    )
    return 2 * len(titled) + shown + 4


def fold_to_fit(titled, folded, height):
    fitted = set(folded)
    for section, _ in reversed(titled):
        if rows_needed(titled, fitted) <= height:
            break
        fitted.add(section.title)
    return fitted


def section_summary(items, state):
    if DOMAIN_ROW in items:
        return f"ROS domain {state.domain_id}"
    return ", ".join(p.name for p in items if getattr(p, "selected", False))


def draw_section_header(stdscr, y, section, current, folded, summary, fit):
    chevron = "▸" if folded else "▾"
    head = f"{chevron} {section.title}"
    stdscr.addstr(y, 0, "> " if current else "  ")
    stdscr.addstr(y, 2, head, curses.A_BOLD | curses.color_pair(section.color))
    room = stdscr.getmaxyx()[1] - 2 - len(head) - 1
    if folded and summary and room > 2:
        stdscr.addstr(y, 2 + len(head), fit(f"  {summary}", room), curses.A_DIM)
