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


def domain_warning(domain, claims):
    """Warning when another Control Center on this host claims `domain`, else None."""
    sessions = claims.get(domain)
    if not sessions:
        return None
    return f"ROS domain {domain} is already used by {', '.join(sessions)}"


def draw_domain_row(stdscr, y, x, state, current, claims=None):
    core = state.get_by_id("core")
    attr = curses.A_NORMAL if core and core.selected else curses.A_DIM
    pending = state.domain_restart_pending()
    number_attr = curses.color_pair(1) if pending else attr
    label = f"{'> ' if current else '  '}ROS domain ID: < "
    number = str(state.domain_id)
    stdscr.addstr(y, x, label, attr)
    stdscr.addstr(y, x + len(label), number, number_attr)
    end = x + len(label) + len(number)
    stdscr.addstr(y, end, " >", attr)
    warning = domain_warning(state.domain_id, claims or {})
    room = stdscr.getmaxyx()[1] - (end + 2) - 1
    if warning and room > 1:
        try:
            stdscr.addstr(y, end + 2, f" {warning}"[:room], curses.color_pair(2))
        except curses.error:
            pass
