from __future__ import annotations

import curses
from pathlib import Path

import components
import tui_toolbox
import update_status
from tui_toolbox import draw_row, draw_title, fit, put
from update_branches import BranchPicker, current_branch, version

TITLE = "Update Lucy"
HINT = "Up/Down: move  Left/Right: branch  Space: toggle  Esc: exit"
BUTTONS = ("Update", "Exit")
TAG_WIDTH = 16
LONGEST_LABEL = max(len(label) for label in components.LABELS.values())
TAGS = {
    "installed": ("[INSTALLED]", tui_toolbox.GREEN, 0),
    "failed": ("[FAILED]", tui_toolbox.RED, curses.A_BOLD),
    "to install": ("[TO INSTALL]", tui_toolbox.YELLOW, 0),
    "to leave out": ("[LEAVE OUT]", tui_toolbox.YELLOW, 0),
    "not installed": ("[NOT INSTALLED]", 0, curses.A_DIM),
}


def _status_attr(status: str) -> int:
    _, pair, attr = TAGS[status]
    return curses.color_pair(pair) | attr


def _draw_branches(stdscr, y, col, repo, picker, focused) -> None:
    room = stdscr.getmaxyx()[1] - col - 1
    if not focused:
        attr = curses.color_pair(tui_toolbox.YELLOW) if picker.targets[repo] != picker.current[repo] else 0
        put(stdscr, y, col, fit(picker.text(repo), room), attr)
        return
    for i, branch in enumerate(picker.from_target(repo)):
        room = stdscr.getmaxyx()[1] - col - 1
        if room <= 1:
            return
        col = put(stdscr, y, col, fit(branch, room), curses.A_REVERSE if i == 0 else curses.A_DIM) + 2


def _draw_line(stdscr, y, width, focused, checkbox, label, status, repo, picker) -> None:
    tag, _, _ = TAGS[status]
    col = draw_row(stdscr, y, 2, "> " if focused else "  ", "", checkbox, f"{label[:width]:<{width}}",
                   curses.A_BOLD if focused else 0, f" {tag:<{TAG_WIDTH - 1}}", _status_attr(status))
    if repo in picker.targets:
        _draw_branches(stdscr, y, col + 1, repo, picker, focused)


def _draw(stdscr, root, selection, picker, focus, workspace_branch, current) -> None:
    stdscr.erase()
    w = stdscr.getmaxyx()[1]
    width = max(20, min(LONGEST_LABEL, w - 41))
    draw_title(stdscr, f"{TITLE} {version(Path(root))}")
    stdscr.addstr(1, 2, f"      {'Component':<{width}} {'Status':<{TAG_WIDTH - 1}} Branch"[: w - 3], curses.A_DIM)
    y = 2
    for i, name in enumerate(focus):
        if name in components.LABELS:
            _draw_line(stdscr, y, width, i == current, "[x]" if selection[name] else "[ ]", components.LABELS[name],
                       update_status.status(root, name, selection[name]), components.REPOS.get(name), picker)
        else:
            _draw_line(stdscr, y, width, i == current, "   ", name, update_status.core_status(root, name), name, picker)
        y += 1
    col = draw_row(stdscr, y, 2, "  ", "", "   ", f"{update_status.WORKSPACE:<{width}}", 0,
                   f" {TAGS['installed'][0]:<{TAG_WIDTH - 1}}", _status_attr("installed"))
    put(stdscr, y, col + 1, fit(workspace_branch, w - col - 2))
    problems = components.problems(selection)
    note, status = ("; ".join(problems), "failed") if problems else update_status.summary(root, selection)
    put(stdscr, y + 1, 2, fit(note, w - 3), _status_attr(status))
    x = 4
    for i, button in enumerate(BUTTONS):
        x = put(stdscr, y + 2, x, f"[ {button} ]", curses.A_REVERSE if len(focus) + i == current else 0) + 2
    focused = focus[current] if current < len(focus) else None
    hint = picker.details.get(components.REPOS.get(focused, focused), HINT)
    put(stdscr, stdscr.getmaxyx()[0] - 1, 2, fit(hint, w - 3), curses.A_DIM)
    stdscr.refresh()


def update_screen(stdscr, root) -> bool:
    curses.curs_set(0)
    tui_toolbox.setup_colors()
    selection = components.load(root)
    picker = BranchPicker(root)
    focus = [*components.LABELS, *update_status.core_repos(root)]
    workspace_branch = current_branch(Path(root))
    stops = len(focus) + len(BUTTONS)
    current = len(focus)
    while True:
        _draw(stdscr, root, selection, picker, focus, workspace_branch, current)
        key = stdscr.getch()
        on_button = current >= len(focus)
        name = None if on_button else focus[current]
        repo = components.REPOS.get(name, name)
        if key == curses.KEY_UP:
            current = (current - 1) % stops
        elif key == curses.KEY_DOWN:
            current = (current + 1) % stops
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
            delta = 1 if key == curses.KEY_RIGHT else -1
            if on_button:
                current = len(focus) + (current - len(focus) + delta) % len(BUTTONS)
            elif repo in picker.targets:
                picker.shift(repo, delta)
        elif key in (ord(" "), ord("\n"), ord("\r")):
            if name in selection:
                selection[name] = not selection[name]
            elif on_button and BUTTONS[current - len(focus)] == "Exit":
                return False
            elif on_button and not components.problems(selection):
                components.save(root, selection)
                picker.save()
                return True
        elif key in (ord("q"), ord("Q"), 27):
            return False
