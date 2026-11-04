from __future__ import annotations

import curses
from pathlib import Path

import tui_toolbox
import update_progress
import update_split
from tui_toolbox import draw_row, draw_title, fit, put

TITLE = "Updating Lucy"
REFRESH_MS = 500
LABEL_WIDTH = 60
RUNNING_HINT = "Drag in the logs to copy them"
CHECK_COLORS = {
    "done": (tui_toolbox.GREEN, 0),
    "running": (tui_toolbox.YELLOW, curses.A_BOLD),
    "next": (0, curses.A_DIM),
    "failed": (tui_toolbox.RED, curses.A_BOLD),
}


def visible(steps: list[dict], room: int) -> list[dict]:
    active = next((i for i, row in enumerate(steps) if row["state"] != "done"), len(steps))
    start = max(0, min(active - 2, len(steps) - room))
    return steps[start:start + room]


def finished_hint(root) -> str:
    exit_file = Path(root) / update_split.EXIT_FILE
    if not exit_file.is_file():
        return RUNNING_HINT
    return f"Finished with exit code {exit_file.read_text().strip()}: press Enter in the logs"


def draw(stdscr, root) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    draw_title(stdscr, TITLE)
    steps = update_progress.read(root)
    if not steps:
        put(stdscr, 2, 2, fit("Preparing...", w - 3), curses.A_DIM)
    for i, row in enumerate(visible(steps, max(1, h - 4))):
        pair, attr = CHECK_COLORS[row["state"]]
        draw_row(stdscr, 2 + i, 2, "> " if row["state"] == "running" else "  ", "",
                 "[x]" if row["state"] == "done" else "[ ]", row["label"][:LABEL_WIDTH],
                 curses.A_BOLD if row["state"] == "running" else 0, "", 0, curses.color_pair(pair) | attr)
    put(stdscr, h - 1, 2, fit(finished_hint(root), w - 3), curses.A_DIM)
    stdscr.refresh()


def watch(stdscr, root) -> None:
    curses.curs_set(0)
    tui_toolbox.setup_colors()
    stdscr.timeout(REFRESH_MS)
    while True:
        try:
            draw(stdscr, root)
        except curses.error:
            pass
        stdscr.getch()


if __name__ == "__main__":
    curses.wrapper(watch, ".")
