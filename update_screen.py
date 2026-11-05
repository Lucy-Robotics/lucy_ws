from __future__ import annotations

import curses
from dataclasses import dataclass, field
from pathlib import Path

import components
import tui_toolbox
import update_status
from tui_toolbox import draw_row, draw_title, fit, put
from update_branches import WORKSPACE, BranchPicker, version

TITLE = "Update Lucy"
HINT = "Up/Down: move  Right: branch  Space: toggle  X: exit"
EDIT_HINT = "Up/Down: pick a branch  Left: back  X: exit"
BUTTONS = ("Update", "Exit")
FIRST_ROW = 2
LABEL_WIDTH = max(len(label) for label in components.LABELS.values())
BRANCH_COLUMN = 2 + len("> [x] ") + LABEL_WIDTH + 1
CHECK_COLORS = {
    "installed": (tui_toolbox.GREEN, 0),
    "failed": (tui_toolbox.RED, curses.A_BOLD),
    "to install": (tui_toolbox.YELLOW, 0),
    "to leave out": (tui_toolbox.YELLOW, 0),
    "not installed": (0, curses.A_DIM),
}


@dataclass
class Screen:
    root: str
    selection: dict[str, bool]
    picker: BranchPicker
    focus: list[str]
    current: int = 0
    editing: bool = False
    version: str = field(default="")

    @property
    def focused(self) -> str | None:
        return self.focus[self.current] if self.current < len(self.focus) else None

    @property
    def focused_repo(self) -> str | None:
        repo = components.REPOS.get(self.focused, self.focused)
        return repo if repo in self.picker.targets else None

    def left_out(self) -> set[str]:
        return components.left_out_repos(self.selection)


def _row(screen: Screen, name: str) -> tuple[str, str, str, str | None]:
    if name in components.LABELS:
        on = screen.selection[name]
        return ("[x]" if on else "[ ]", components.LABELS[name],
                update_status.status(screen.root, name, on), components.REPOS.get(name))
    if name == WORKSPACE:
        return "[x]", name, "installed", name
    return "[x]", name, update_status.core_status(screen.root, name), name


def check_attr(status: str, pending: bool) -> int:
    pair, attr = (tui_toolbox.YELLOW, 0) if pending else CHECK_COLORS[status]
    return curses.color_pair(pair) | attr


def _draw_rows(stdscr, screen: Screen, room: int) -> None:
    for i, name in enumerate(screen.focus):
        checkbox, label, status, repo = _row(screen, name)
        focused = i == screen.current
        pending = repo in screen.picker.targets and repo not in screen.left_out() and screen.picker.pending(repo)
        draw_row(stdscr, FIRST_ROW + i, 2, "> " if focused and not screen.editing else "  ", "", checkbox,
                 f"{label:<{LABEL_WIDTH}}", curses.A_BOLD if focused else 0, "", 0, check_attr(status, pending))
        if screen.focused_repo is None and repo in screen.picker.targets:
            put(stdscr, FIRST_ROW + i, BRANCH_COLUMN, fit(screen.picker.text(repo), room))


def _branch_attr(screen: Screen, repo: str, branch: str) -> int:
    if branch == screen.picker.targets[repo]:
        return curses.A_REVERSE if screen.editing else curses.A_BOLD
    return curses.color_pair(tui_toolbox.CYAN) if branch == screen.picker.current[repo] else curses.A_DIM


def _draw_branch_list(stdscr, screen: Screen, room: int) -> None:
    repo = screen.focused_repo
    options = screen.picker.options[repo]
    picked = options.index(screen.picker.targets[repo])
    for i in range(len(screen.focus)):
        index = picked + i - screen.current
        if 0 <= index < len(options):
            put(stdscr, FIRST_ROW + i, BRANCH_COLUMN, fit(options[index], room),
                _branch_attr(screen, repo, options[index]))


def _note(screen: Screen) -> tuple[str, str]:
    problems = components.problems(screen.selection)
    if problems:
        return "; ".join(problems), "failed"
    text, status = update_status.summary(screen.root, screen.selection)
    changes = screen.picker.changes(screen.left_out())
    if status == "failed" or not changes:
        return text, status
    return f"Switching: {', '.join(changes)}", "to install"


def _draw(stdscr, screen: Screen) -> None:
    stdscr.erase()
    w = stdscr.getmaxyx()[1]
    room = w - BRANCH_COLUMN - 1
    draw_title(stdscr, f"{TITLE} {screen.version}")
    stdscr.addstr(1, 2, f"      {'Component':<{LABEL_WIDTH}} Branch"[: w - 3], curses.A_DIM)
    _draw_rows(stdscr, screen, room)
    if screen.focused_repo is not None:
        _draw_branch_list(stdscr, screen, room)
    y = FIRST_ROW + len(screen.focus)
    note, status = _note(screen)
    put(stdscr, y, 2, fit(note, w - 3), check_attr(status, False))
    x = 4
    for i, button in enumerate(BUTTONS):
        x = put(stdscr, y + 1, x, f"[ {button} ]", curses.A_REVERSE if len(screen.focus) + i == screen.current else 0) + 2
    hint = EDIT_HINT if screen.editing else screen.picker.details.get(screen.focused_repo, HINT)
    put(stdscr, stdscr.getmaxyx()[0] - 1, 2, fit(hint, w - 3), curses.A_DIM)
    stdscr.refresh()


def _edit_branch(screen: Screen, key: int) -> None:
    if key in (curses.KEY_UP, curses.KEY_DOWN):
        screen.picker.shift(screen.focused_repo, 1 if key == curses.KEY_DOWN else -1)
        screen.picker.save()
    elif key in (curses.KEY_LEFT, ord(" "), ord("\n"), ord("\r"), ord("q"), ord("Q"), 27):
        screen.editing = False


def update_screen(stdscr, root) -> str | None:
    curses.curs_set(0)
    tui_toolbox.setup_colors()
    focus = [*update_status.offered(root), *update_status.core_repos(root), WORKSPACE]
    screen = Screen(root, components.load(root), BranchPicker(root), focus, len(focus), version=version(Path(root)))
    stops = len(focus) + len(BUTTONS)
    while True:
        _draw(stdscr, screen)
        key = stdscr.getch()
        if key in (ord("x"), ord("X")):
            return None
        if screen.editing:
            _edit_branch(screen, key)
            continue
        on_button = screen.current >= len(focus)
        if key == curses.KEY_UP:
            screen.current = (screen.current - 1) % stops
        elif key == curses.KEY_DOWN:
            screen.current = (screen.current + 1) % stops
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT) and on_button:
            step = 1 if key == curses.KEY_RIGHT else -1
            screen.current = len(focus) + (screen.current - len(focus) + step) % len(BUTTONS)
        elif key == curses.KEY_RIGHT and screen.focused_repo is not None:
            screen.editing = True
        elif key in (ord(" "), ord("\n"), ord("\r")):
            if screen.focused in screen.selection:
                screen.selection[screen.focused] = not screen.selection[screen.focused]
                if not components.problems(screen.selection):
                    components.save_repos(root, screen.selection)
            elif on_button and BUTTONS[screen.current - len(focus)] == "Exit":
                return None
            elif on_button and not components.problems(screen.selection):
                components.save(root, screen.selection)
                return screen.picker.targets.get(WORKSPACE, "")
        elif key in (ord("q"), ord("Q"), 27):
            return None
