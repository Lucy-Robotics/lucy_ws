"""Curses TUI rendering and main event loop."""

import time

try:
    import curses
except ImportError:
    curses = None

from .apply import apply_changes, default_robot_selection, restore_selection
from .autostart import autostart
from .choices import settle_selection
from .config import get_dev_mode, load_config, save_selection
from .constants import (
    DEFAULT_TMUX_SESSION,
    MIN_TERM_WIDTH,
    REDRAW_INTERVAL_MS,
    TMUX_SESSION,
)
from .domain import export_domain_id
from .domain_field import DOMAIN_ROW, domain_step, draw_domain_row
from .sections import (
    SectionRow,
    draw_section_header,
    fold_change,
    fold_to_fit,
    rows_needed,
    section_summary,
)
from .links import ADD_INTERFACE, ADD_ROBOT, LinkRow, draw_link_row, open_link
from .instance import claim_domains, other_instance_domains
from .robot_switch import take_robot_request
from .stack_status import write_stack_status
from .state import (
    LauncherState,
    StatusPoller,
    _has_unapplied_changes,
    _intended_running,
    _nav_hint,
    _pkg_start_times,
    _pkg_stop_times,
    _stage_hint,
    _status_url,
    get_pkg_status,
)


def _fit(text, room):
    """Shorten a trailing "..."-suffixed stage readout to `room` columns.

    The stage is the last thing on the row and the first to run off the end of a
    terminal at MIN_TERM_WIDTH — where an addstr past the last column raises,
    taking the rest of the row with it. The suffix goes first: it is decoration
    the "n/N" counter already carries, and dropping it is often enough to keep
    the label whole. Only when that is not enough is the label itself cut, with
    the suffix put back to mark the cut — an ASCII "..." and not an ellipsis
    character, because the launcher never calls setlocale() and curses would
    encode one against the C locale's ASCII codec, raising a UnicodeEncodeError
    that is not a curses.error and so not caught below."""
    if len(text) <= room:
        return text
    stripped = text.rstrip(".")
    if len(stripped) <= room:
        return stripped
    return (stripped[: max(0, room - 3)].rstrip(" .") + "...")[:room]


FOOTER = "Enter: Apply | Space: Toggle | Q/X/Esc: Stop All & Exit"
SHORT_FOOTER = "Enter Apply | Space Toggle | Q Exit"
UNAPPLIED = "Unapplied changes — press Enter to apply"


def _draw_pkg_row(
    stdscr,
    y,
    x,
    prefix,
    indent,
    checkbox,
    name,
    attr,
    status,
    hint="",
    url="",
    stage="",
):
    labels = {
        "running": (" [RUNNING]", curses.color_pair(4)),
        "loading": (" [LOADING]", curses.color_pair(1)),
        "stopping": (" [STOPPING]", curses.color_pair(1)),
        "crashed": (" [CRASHED]", curses.color_pair(2) | curses.A_BOLD),
        "stopped": (" [STOPPED]", curses.A_DIM),
    }
    status_str, status_attr = labels.get(status, ("", curses.A_DIM))
    head = f"{prefix}{indent}{checkbox} "
    room = stdscr.getmaxyx()[1] - x - len(head) - len(status_str) - 1
    base = head + _fit(name, max(room, 0))
    stdscr.addstr(y, x, base, attr)
    col = x + len(base)
    try:
        stdscr.addstr(y, col, status_str, status_attr)
        col += len(status_str)
    except curses.error:
        pass
    if stage:
        # Dimmed: the stage is a progress readout, not a state of its own, and
        # must not compete with the status label it trails.
        room = stdscr.getmaxyx()[1] - col - 1
        if room > 1:
            text = _fit(f" {stage}", room)
            try:
                stdscr.addstr(y, col, text, curses.A_DIM)
                col += len(text)
            except curses.error:
                pass
    if url and status == "running":
        text = _fit(f" ({url})", stdscr.getmaxyx()[1] - col - 1)
        try:
            stdscr.addstr(y, col, text, curses.color_pair(3))
            col += len(text)
        except curses.error:
            pass
    if hint:
        text = _fit(f" {hint}", stdscr.getmaxyx()[1] - col - 1)
        try:
            stdscr.addstr(y, col, text, curses.color_pair(3))
            col += len(text)
        except curses.error:
            pass


def confirm_exit_action(key):
    """What a keypress means while the exit prompt is up.

    Navigation keeps the prompt standing: the status rows update underneath it
    on every tick, and an answer that only survived until the next repaint would
    be impossible to give. Anything else dismisses it, so no keystroke can
    confirm a teardown by accident."""
    if key in (ord("y"), ord("Y")):
        return "confirm"
    if key in (curses.KEY_UP, curses.KEY_DOWN):
        return "keep"
    return "dismiss"


def draw_too_small_message(stdscr, min_height):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    message = "Please increase terminal size"
    message2 = f"({MIN_TERM_WIDTH}x{min_height} required)"
    stdscr.addstr(h // 2 - 1, max(0, (w - len(message)) // 2), message, curses.A_BOLD)
    stdscr.addstr(h // 2, max(0, (w - len(message2)) // 2), message2, curses.A_DIM)
    stdscr.refresh()


def _is_mode(p):
    return p.type == "modifier" and not p.requires_pkg and p.section != "tools"


def launch_sections(state):
    robots = [p for p in state.packages if p.type == "modifier" and p.requires_pkg] + [
        ADD_ROBOT
    ]
    cores = [p for p in state.packages if p.type == "core"]
    modes = [p for p in state.packages if _is_mode(p)]
    interfaces = [p for p in state.packages if p.type == "interface"] + [ADD_INTERFACE]
    tools = [p for p in state.packages if p.type == "tool" or p.section == "tools"]
    return [
        (SectionRow("Stack", 1), cores + modes),
        (SectionRow("Robot", 1), robots),
        (SectionRow("Control Interfaces", 3), interfaces),
        (SectionRow("Tools", 3), tools),
        (SectionRow("Options", 3), [DOMAIN_ROW]),
    ]


def draw_tui(
    stdscr,
    state,
    current_idx,
    error_msg,
    status_msg,
    unapplied=False,
    confirm_exit=False,
    folded=frozenset(),
):
    titled = launch_sections(state)
    h, w = stdscr.getmaxyx()
    all_folded = {section.title for section, _ in titled}
    min_height = rows_needed(titled, all_folded)
    folded = fold_to_fit(titled, folded, h)
    display_list = []
    for section, items in titled:
        display_list += [section] + ([] if section.title in folded else items)
    if h < min_height or w < MIN_TERM_WIDTH:
        draw_too_small_message(stdscr, min_height)
        return None

    stdscr.erase()
    title = "Lucy Launch Screen"
    if TMUX_SESSION != DEFAULT_TMUX_SESSION:
        title += f" ({TMUX_SESSION})"
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
    footer = FOOTER if len(FOOTER) + 3 <= w else SHORT_FOOTER
    stdscr.addstr(h - 1, 2, footer, curses.A_BOLD)

    if confirm_exit:
        stdscr.addstr(
            h - 2,
            2,
            "Stop all processes and exit? (y/n)",
            curses.A_BOLD | curses.color_pair(2),
        )
    elif status_msg:
        stdscr.addstr(h - 2, 2, _fit(status_msg, w - 3), curses.A_BOLD)
    elif error_msg:
        stdscr.addstr(
            h - 2, 2, _fit(f"Warning: {error_msg}", w - 3), curses.color_pair(2)
        )
    elif unapplied:
        stdscr.addstr(h - 2, 2, _fit(UNAPPLIED, w - 3), curses.color_pair(1))

    def draw_items(items, offset, x=4):
        nonlocal row
        for i, p in enumerate(items):
            list_idx = offset + i
            if isinstance(p, LinkRow):
                draw_link_row(stdscr, row + i, x, p, current_idx == list_idx)
                continue
            if p is DOMAIN_ROW:
                draw_domain_row(stdscr, row + i, 4, state, current_idx == list_idx)
                continue
            prefix = "> " if current_idx == list_idx else "  "
            checkbox = "[x]" if p.selected else "[ ]"
            can_enable = all(state.get_by_id(dep).selected for dep in p.dependencies)
            attr = curses.A_NORMAL if can_enable else curses.A_DIM
            if p.type == "core":
                attr |= curses.A_BOLD
            if p.subitem:
                indent = "        "
            elif _is_mode(p):
                indent = "    "
            else:
                indent = ""
            status = get_pkg_status(p)
            shows_stopped = p.type == "core" or p.selected
            label = status if shows_stopped or status != "stopped" else None
            hint = _nav_hint(p)
            _draw_pkg_row(
                stdscr,
                row + i,
                x,
                prefix,
                indent,
                checkbox,
                p.name,
                attr,
                label,
                hint,
                _status_url(p),
                _stage_hint(p, status),
            )
        row += len(items)

    row = 2
    offset = 0
    for section, items in titled:
        row += 1
        is_folded = section.title in folded
        summary = section_summary(items, state)
        draw_section_header(
            stdscr, row, section, current_idx == offset, is_folded, summary, _fit
        )
        row += 1
        offset += 1
        if not is_folded:
            draw_items(items, offset)
            offset += len(items)

    stdscr.refresh()
    return display_list


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)
    curses.start_color()
    curses.use_default_colors()

    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_YELLOW, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)
        curses.init_pair(4, curses.COLOR_GREEN, -1)

    state = LauncherState(load_config())
    restore_selection(state)
    default_robot_selection(state)
    settle_selection(state)
    state.avoid_domains(other_instance_domains())
    export_domain_id(state.domain_id)
    claim_domains(state.claimed_domains())
    status_msg = autostart(state, get_dev_mode())
    status_msg_until = time.time() + 3.0 if status_msg else 0.0

    poller = StatusPoller(state)
    try:
        return _event_loop(stdscr, state, poller, status_msg, status_msg_until)
    finally:
        poller.stop()


def _event_loop(stdscr, state, poller, status_msg=None, status_msg_until=0.0):
    """Draw/input loop. Package status arrives from `poller` as finished
    snapshots so no keystroke ever waits on a readiness probe."""
    current_idx = 0
    error_msg = None
    error_until = 0.0
    confirm_exit = False
    folded = set()

    while True:
        try:
            snapshot = poller.take()
            if snapshot is not None:
                state.apply_snapshot(snapshot)
            write_stack_status(state)
            switched = take_robot_request(state)
            if switched:
                apply_changes(state)
                save_selection({p.id for p in state.packages if p.selected})
                status_msg = f"Control panel switched to {switched.name}"
                status_msg_until = time.time() + 5.0
                poller.request_refresh()
            if status_msg and time.time() >= status_msg_until:
                status_msg = None
            height = stdscr.getmaxyx()[0]
            folded = fold_to_fit(launch_sections(state), folded, height)
            display_list = draw_tui(
                stdscr,
                state,
                current_idx,
                error_msg,
                status_msg,
                _has_unapplied_changes(state),
                confirm_exit,
                folded,
            )
            if error_msg and time.time() >= error_until:
                error_msg = None
            if display_list is not None:
                current_idx = min(current_idx, len(display_list) - 1)

            if display_list is None:
                stdscr.nodelay(1)
                stdscr.timeout(100)
                key = stdscr.getch()
                if key != curses.KEY_RESIZE:
                    time.sleep(0.1)
                continue

            # A refresh runs every readiness check, ~120ms for core's stages, on
            # the poller thread. Transitions poll at 2Hz to keep the displayed
            # stage current; a settled stack changes only when something breaks.
            if _pkg_start_times or _pkg_stop_times:
                poller.set_interval(0.5)
            elif _intended_running:
                poller.set_interval(5.0)
            else:
                poller.set_interval(None)

            # Statuses also age on their own (LOADING and STOPPING both expire on
            # a clock), so redraw on a short tick whenever anything is live. The
            # redraw is cheap: erase() leaves curses sending only what changed.
            if _intended_running or _pkg_stop_times or status_msg or error_msg:
                stdscr.nodelay(1)
                stdscr.timeout(REDRAW_INTERVAL_MS)
            else:
                stdscr.nodelay(0)
                stdscr.timeout(-1)
            key = stdscr.getch()
            if key == -1 or key == curses.KEY_RESIZE:
                continue

            if confirm_exit:
                action = confirm_exit_action(key)
                if action == "confirm":
                    return "ExitWorkspace", state
                if action == "dismiss":
                    confirm_exit = False
                    continue

            current = display_list[current_idx]
            on_domain = current is DOMAIN_ROW
            if isinstance(current, SectionRow):
                fold = fold_change(key, current.title in folded)
                if fold:
                    folded.add(current.title)
                elif fold is False:
                    opened = folded - {current.title}
                    if rows_needed(launch_sections(state), opened) > height:
                        error_msg = f"Terminal too small to open {current.title}"
                        error_until = time.time() + 3.0
                    else:
                        folded = opened
                if fold is not None:
                    continue
            if key == curses.KEY_UP:
                current_idx = (current_idx - 1) % len(display_list)
            elif key == curses.KEY_DOWN:
                current_idx = (current_idx + 1) % len(display_list)
            elif isinstance(current, LinkRow) and key in (ord(" "), ord("\n")):
                status_msg = open_link(current)
                status_msg_until = time.time() + 5.0
            elif on_domain and (step := domain_step(key)):
                state.step_domain(step, other_instance_domains())
                claim_domains(state.claimed_domains())
            elif key == ord(" "):
                if not on_domain:
                    error_msg = state.toggle(current.id)
                    error_until = time.time() + 3.0
            elif key == ord("\n"):
                apply_changes(state)
                claim_domains(state.claimed_domains())
                save_selection(
                    {p.id for p in state.packages if p.selected}, state.domain_id
                )
                status_msg = "Configuration Applied!"
                status_msg_until = time.time() + 2.0
                poller.request_refresh()
            elif key in [ord("x"), ord("X"), ord("q"), ord("Q"), 27]:
                confirm_exit = True

        except curses.error:
            time.sleep(0.1)
            continue
