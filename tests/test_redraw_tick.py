import pytest

from launcher import domain_field, links, tui

KEY_RESIZE = 1003


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    KEY_UP, KEY_DOWN, KEY_RESIZE = 1001, 1002, KEY_RESIZE
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self, keys):
        self.keys = list(keys)
        self.timeouts = []

    def getmaxyx(self):
        return (80, 120)

    def erase(self):
        pass

    def refresh(self):
        pass

    def addstr(self, *_args):
        pass

    def nodelay(self, _flag):
        pass

    def timeout(self, ms):
        self.timeouts.append(ms)

    def getch(self):
        return self.keys.pop(0)


class _Poller:
    def take(self):
        return None

    def set_interval(self, _seconds):
        pass


@pytest.fixture
def state(isolated_state, monkeypatch):
    for module in (tui, domain_field, links):
        monkeypatch.setattr(module, "curses", _Curses())
    monkeypatch.setattr(tui, "write_stack_status", lambda _s: None)
    monkeypatch.setattr(tui, "take_robot_request", lambda _s: None)
    return isolated_state


def _timeouts(state, status_msg):
    screen = _Screen([KEY_RESIZE, ord("x"), ord("y")])
    tui._event_loop(screen, state, _Poller(), status_msg, 1e18)
    return screen.timeouts


def test_the_loop_ticks_while_a_status_message_is_showing(state):
    assert _timeouts(state, "Opened https://example.org")[0] == tui.REDRAW_INTERVAL_MS


def test_the_loop_blocks_on_input_with_nothing_live(state):
    assert _timeouts(state, None)[0] == -1
