try:
    import curses
except ImportError:
    curses = None

DOMAIN_ROW = object()


def domain_step(key):
    if key in (curses.KEY_RIGHT, ord("+"), ord("=")):
        return 1
    if key in (curses.KEY_LEFT, ord("-")):
        return -1
    return 0


def domain_hint(state, current):
    if state.domain_restart_pending():
        return (
            f" core runs on {state.running_domain_id}, Enter restarts it",
            curses.color_pair(1),
        )
    if current:
        return " Left/Right to change", curses.A_DIM
    return "", curses.A_DIM


def draw_domain_row(stdscr, y, x, state, current):
    prefix = "> " if current else "  "
    base = f"{prefix}ROS domain ID: < {state.domain_id} >"
    core = state.get_by_id("core")
    stdscr.addstr(
        y, x, base, curses.A_NORMAL if core and core.selected else curses.A_DIM
    )
    hint, attr = domain_hint(state, current)
    room = stdscr.getmaxyx()[1] - (x + len(base)) - 1
    if hint and room > 1:
        try:
            stdscr.addstr(y, x + len(base), hint[:room], attr)
        except curses.error:
            pass
