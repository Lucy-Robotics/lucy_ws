import os
import shutil
import subprocess
import sys
import time
from collections import namedtuple

try:
    import curses
except ImportError:
    curses = None

LinkRow = namedtuple("LinkRow", "name url")

ADD_ROBOT = LinkRow("Add yours", "https://github.com/Lucy-Robotics/lucy_ws")
ADD_INTERFACE = LinkRow(
    "Add yours",
    "https://docs.lucy-robotics.com/share/p1x9ikjkhf/p/"
    "creating-a-new-lucy-interface-aI3ImXSwM7",
)
FEEDBACK_SECONDS = 3
_results = {}


def _opener():
    if sys.platform == "darwin":
        return "open"
    has_desktop = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    return "xdg-open" if has_desktop and shutil.which("xdg-open") else None


def _launch(url):
    if os.name == "nt":
        os.startfile(url)
        return True
    opener = _opener()
    if opener is None:
        return False
    subprocess.Popen(
        [opener, url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def open_link(link):
    try:
        opened = _launch(link.url)
    except OSError:
        opened = False
    _results[link] = (opened, time.monotonic())
    return f"Opened {link.url}" if opened else f"Open in a browser: {link.url}"


def link_feedback(link):
    opened, at = _results.get(link, (None, 0.0))
    if opened is None or time.monotonic() - at > FEEDBACK_SECONDS:
        return None
    if opened:
        return " opened", curses.color_pair(4)
    return " can't open", curses.color_pair(2)


def draw_link_row(stdscr, y, x, link, current):
    stdscr.addstr(y, x, "> " if current else "  ")
    italic = getattr(curses, "A_ITALIC", curses.A_NORMAL)
    text = f" \u2197  {link.name}"
    stdscr.addstr(y, x + 2, text, italic)
    feedback = link_feedback(link)
    if feedback:
        stdscr.addstr(y, x + 2 + len(text), *feedback)
