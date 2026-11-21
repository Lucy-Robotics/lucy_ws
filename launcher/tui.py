"""Curses TUI rendering and main event loop."""

import time

try:
    import curses
except ImportError:
    curses = None

from tui_toolbox import CYAN, GREEN, RED, YELLOW, draw_title, fit, put, setup_colors

from .access_urls import access_urls
from .apply import apply_changes, default_robot_selection, restore_selection
from .autostart import autostart
from .choices import settle_selection
from .clipboard import copied_message
from .config import get_dev_mode, load_config, save_selection
from .constants import (
    MIN_TERM_WIDTH,
    REDRAW_INTERVAL_MS,
    TMUX_SESSION,
)
from .domain import export_domain_id
from .domain_field import DOMAIN_ROW, domain_step, domain_warning, draw_domain_row
from .sections import (
    SectionRow,
    draw_section_header,
    fold_change,
    fold_to_fit,
    rows_needed,
    section_summary,
)
from .links import ADD_INTERFACE, ADD_ROBOT, LinkRow, draw_link_row, open_link
from .instance import claim_domains, other_instance_claims, other_instance_domains
from .options import with_focused_options
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
    _crash_hint,
    _stage_hint,
    get_pkg_status,
)

TMUX_COPIED_KEY = curses.KEY_F12 if curses else None


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
    urls=(),
    stage="",
    detail="",
):
    labels = {
        "running": (" [RUNNING]", curses.color_pair(GREEN)),
        "loading": (" [LOADING]", curses.color_pair(YELLOW)),
        "stopping": (" [STOPPING]", curses.color_pair(YELLOW)),
        "crashed": (" [CRASHED]", curses.color_pair(RED) | curses.A_BOLD),
        "stopped": (" [STOPPED]", curses.A_DIM),
    }
    status_str, status_attr = labels.get(status, ("", curses.A_DIM))
    head = f"{prefix}{indent}{checkbox} "
    room = stdscr.getmaxyx()[1] - x - len(head) - len(status_str) - 1
    base = head + fit(name, max(room, 0))
    stdscr.addstr(y, x, base, attr)
    col = x + len(base)
    col = put(stdscr, y, col, status_str, status_attr)
    if detail and status == "crashed":
        room = stdscr.getmaxyx()[1] - col - 1
        if room > 1:
            col = put(stdscr, y, col, fit(f" {detail}", room), curses.color_pair(RED))
    if stage:
        # Dimmed: the stage is a progress readout, not a state of its own, and
        # must not compete with the status label it trails.
        room = stdscr.getmaxyx()[1] - col - 1
        if room > 1:
            col = put(stdscr, y, col, fit(f" {stage}", room), curses.A_DIM)
    if urls and status == "running":
        room = stdscr.getmaxyx()[1] - col - 1
        text = fit(f" ({'  '.join(urls)})", room) if room > 1 else ""
        col = put(stdscr, y, col, text, curses.color_pair(CYAN))
    if hint:
        text = fit(f" {hint}", stdscr.getmaxyx()[1] - col - 1)
        col = put(stdscr, y, col, text, curses.color_pair(CYAN))


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


def launch_sections(state, focused_id=None):
    """Sections and their rows; a package's options show while it or one of them has the cursor."""
    robots = [p for p in state.packages if p.type == "modifier" and p.requires_pkg] + [
        ADD_ROBOT
    ]
    cores = [p for p in state.packages if p.type == "core"]
    modes = [p for p in state.packages if _is_mode(p)]
    interfaces = with_focused_options(
        [p for p in state.packages if p.type == "interface"], state.packages, focused_id
    ) + [ADD_INTERFACE]
    tools = [p for p in state.packages if p.type == "tool" or p.section == "tools"]
    return [
        (SectionRow("Stack", YELLOW), cores + modes),
        (SectionRow("Robot", YELLOW), robots),
        (SectionRow("Control Interfaces", CYAN), interfaces),
        (SectionRow("Tools", CYAN), tools),
        (SectionRow("Options", CYAN), [DOMAIN_ROW]),
    ]


def display_rows(titled, folded):
    rows = []
    for section, items in titled:
        rows += [section] + ([] if section.title in folded else items)
    return rows


def resolve_focus(state, focused, current_idx, folded, height):
    """``(focused row, its index, folded)``. Option rows come and go with the cursor, so
    the cursor follows its row rather than an index; a row that left (folded away) hands
    the cursor to the one now at its index. Folds fit the rows without options: the
    cursor passing over a package must not fold a section for good."""
    folded = fold_to_fit(launch_sections(state), folded, height)
    for _ in range(2):
        rows = display_rows(launch_sections(state, getattr(focused, "id", None)), folded)
        if focused in rows:
            break
        focused = rows[min(current_idx, len(rows) - 1)]
    return focused, rows.index(focused), folded


def draw_tui(
    stdscr,
    state,
    current_idx,
    error_msg,
    status_msg,
    unapplied=False,
    confirm_exit=False,
    folded=frozenset(),
    domain_claims=None,
    focused_id=None,
):
    titled = launch_sections(state, focused_id)
    h, w = stdscr.getmaxyx()
    # Fit without the options under the cursor; rows they push past the screen are clipped.
    fitted = launch_sections(state)
    all_folded = {section.title for section, _ in fitted}
    min_height = rows_needed(fitted, all_folded)
    folded = fold_to_fit(fitted, folded, h)
    display_list = display_rows(titled, folded)
    if h < min_height or w < MIN_TERM_WIDTH:
        draw_too_small_message(stdscr, min_height)
        return None

    stdscr.erase()
    draw_title(stdscr, f"Lucy Launch Screen ({TMUX_SESSION})")
    footer = FOOTER if len(FOOTER) + 3 <= w else SHORT_FOOTER
    stdscr.addstr(h - 1, 2, footer, curses.A_BOLD)

    if confirm_exit:
        stdscr.addstr(
            h - 2,
            2,
            "Stop all processes and exit? (y/n)",
            curses.A_BOLD | curses.color_pair(RED),
        )
    elif status_msg:
        stdscr.addstr(h - 2, 2, fit(status_msg, w - 3), curses.A_BOLD)
    elif error_msg:
        stdscr.addstr(
            h - 2, 2, fit(f"Warning: {error_msg}", w - 3), curses.color_pair(RED)
        )
    elif unapplied:
        stdscr.addstr(h - 2, 2, fit(UNAPPLIED, w - 3), curses.color_pair(YELLOW))

    def draw_items(items, offset, x=4):
        nonlocal row
        for i, p in enumerate(items):
            list_idx = offset + i
            if row + i >= h - 2:
                continue
            if isinstance(p, LinkRow):
                draw_link_row(stdscr, row + i, x, p, current_idx == list_idx)
                continue
            if p is DOMAIN_ROW:
                draw_domain_row(
                    stdscr, row + i, 4, state, current_idx == list_idx, domain_claims
                )
                continue
            prefix = "> " if current_idx == list_idx else "  "
            checkbox = "[x]" if p.selected else "[ ]"
            can_enable = all(state.get_by_id(dep).selected for dep in p.dependencies)
            attr = curses.A_NORMAL if can_enable else curses.A_DIM
            if p.type == "core":
                attr |= curses.A_BOLD
            if p.subitem:
                indent = "        "
            elif _is_mode(p) or p.type == "option":
                indent = "    "
            else:
                indent = ""
            status = None if p.type == "option" else get_pkg_status(p)
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
                access_urls(p, state),
                _stage_hint(p, status),
                _crash_hint(p, status),
            )
        row += len(items)

    row = 1
    offset = 0
    for section, items in titled:
        row += 1
        is_folded = section.title in folded
        summary = section_summary(items, state)
        if row < h - 2:
            draw_section_header(
                stdscr, row, section, current_idx == offset, is_folded, summary, fit
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
    setup_colors()

    state = LauncherState(load_config())
    restore_selection(state)
    default_robot_selection(state)
    settle_selection(state)
    claims = other_instance_claims()
    saved_domain = state.domain_id
    state.avoid_domains(set(claims))
    export_domain_id(state.domain_id)
    claim_domains(state.claimed_domains())
    status_msg = autostart(state, get_dev_mode())
    status_msg_until = time.time() + 3.0 if status_msg else 0.0
    if state.domain_id != saved_domain:
        status_msg = (
            f"{domain_warning(saved_domain, claims)}: switched to {state.domain_id}"
        )
        status_msg_until = time.time() + 8.0

    poller = StatusPoller(state)
    try:
        return _event_loop(stdscr, state, poller, status_msg, status_msg_until)
    finally:
        poller.stop()


def _event_loop(stdscr, state, poller, status_msg=None, status_msg_until=0.0):
    """Draw/input loop. Package status arrives from `poller` as finished
    snapshots so no keystroke ever waits on a readiness probe."""
    current_idx = 0
    focused = None
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
                save_selection(
                    {p.id for p in state.packages if p.selected}, state.domain_id
                )
                status_msg = f"Control panel switched to {switched.name}"
                status_msg_until = time.time() + 5.0
                poller.request_refresh()
            if status_msg and time.time() >= status_msg_until:
                status_msg = None
            height = stdscr.getmaxyx()[0]
            focused, current_idx, folded = resolve_focus(
                state, focused, current_idx, folded, height
            )
            display_list = draw_tui(
                stdscr,
                state,
                current_idx,
                error_msg,
                status_msg,
                _has_unapplied_changes(state),
                confirm_exit,
                folded,
                other_instance_claims(),
                getattr(focused, "id", None),
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
                focused = display_list[current_idx]
            elif key == curses.KEY_DOWN:
                current_idx = (current_idx + 1) % len(display_list)
                focused = display_list[current_idx]
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
            elif key == TMUX_COPIED_KEY:
                status_msg = copied_message()
                status_msg_until = time.time() + 2.0
            elif key in [ord("x"), ord("X"), ord("q"), ord("Q"), 27]:
                confirm_exit = True

        except curses.error:
            time.sleep(0.1)
            continue
