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


def draw_domain_row(stdscr, y, x, state, current):
    core = state.get_by_id("core")
    attr = curses.A_NORMAL if core and core.selected else curses.A_DIM
    pending = state.domain_restart_pending()
    number_attr = curses.color_pair(1) if pending else attr
    label = f"{'> ' if current else '  '}ROS domain ID: < "
    number = str(state.domain_id)
    stdscr.addstr(y, x, label, attr)
    stdscr.addstr(y, x + len(label), number, number_attr)
    stdscr.addstr(y, x + len(label) + len(number), " >", attr)
