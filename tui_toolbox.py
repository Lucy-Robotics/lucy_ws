from __future__ import annotations

try:
    import curses
except ImportError:
    curses = None

YELLOW, RED, CYAN, GREEN = 1, 2, 3, 4


def setup_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    if curses.has_colors():
        for pair, color in ((YELLOW, curses.COLOR_YELLOW), (RED, curses.COLOR_RED),
                            (CYAN, curses.COLOR_CYAN), (GREEN, curses.COLOR_GREEN)):
            curses.init_pair(pair, color, -1)


def fit(text: str, room: int) -> str:
    """Shorten a trailing "..."-suffixed readout to `room` columns.

    The suffix goes first: dropping it is often enough to keep the label whole. Only then
    is the label cut, with an ASCII "..." because the TUIs never call setlocale() and
    curses would encode an ellipsis against the C locale's ASCII codec and raise."""
    if len(text) <= room:
        return text
    stripped = text.rstrip(".")
    if len(stripped) <= room:
        return stripped
    return (stripped[: max(0, room - 3)].rstrip(" .") + "...")[:room]


def put(stdscr, y: int, x: int, text: str, attr: int = 0) -> int:
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        return x
    return x + len(text)


def draw_title(stdscr, title: str) -> None:
    stdscr.addstr(0, max(0, (stdscr.getmaxyx()[1] - len(title)) // 2), title, curses.A_BOLD)


def draw_row(stdscr, y, x, prefix, indent, checkbox, name, attr, tag, tag_attr, checkbox_attr=None) -> int:
    base = f"{prefix}{indent}{checkbox} {name}"
    stdscr.addstr(y, x, base, attr)
    if checkbox_attr is not None:
        put(stdscr, y, x + len(prefix) + len(indent), checkbox, checkbox_attr)
    return put(stdscr, y, x + len(base), tag, tag_attr)
