from __future__ import annotations

import curses

import components

HINT = "Up/Down: move  Space: toggle  Enter: save  Esc: cancel"
APPLY_NOTE = "Update applies a changed choice."


def choose_components(stdscr, root) -> dict[str, bool] | None:
    curses.curs_set(0)
    selection = components.load(root)
    names = list(components.LABELS)
    current = 0
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "Choose what to install"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
        for i, name in enumerate(names):
            prefix = "> " if i == current else "  "
            box = "[x]" if selection[name] else "[ ]"
            stdscr.addstr(2 + i, 4, f"{prefix}{box} {components.LABELS[name]}")
        stdscr.addstr(3 + len(names), 4, APPLY_NOTE, curses.A_DIM)
        stdscr.addstr(h - 2, 2, HINT[: w - 3], curses.A_DIM)
        stdscr.refresh()
        key = stdscr.getch()
        if key == curses.KEY_UP:
            current = (current - 1) % len(names)
        elif key == curses.KEY_DOWN:
            current = (current + 1) % len(names)
        elif key == ord(" "):
            selection[names[current]] = not selection[names[current]]
        elif key in (ord("\n"), ord("\r")):
            components.save(root, selection)
            return selection
        elif key in (ord("q"), ord("Q"), 27):
            return None
