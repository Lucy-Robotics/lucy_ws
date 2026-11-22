import subprocess

import pytest

from launcher import domain_field, links, tui
from launcher.links import ADD_ROBOT, FEEDBACK_SECONDS


class _Curses:
    A_BOLD, A_DIM, A_NORMAL = 1, 2, 0
    error = Exception

    def color_pair(self, n):
        return n << 8


class _Screen:
    def __init__(self):
        self.writes = []

    def addstr(self, y, x, text, attr=0):
        self.writes.append((y, x, text, attr))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(links, "curses", _Curses())
    monkeypatch.setattr(links, "_results", {})
    monkeypatch.setattr(links.os, "name", "posix")
    monkeypatch.setattr(links.sys, "platform", "linux")
    monkeypatch.setattr(links.shutil, "which", lambda _n: "/usr/bin/xdg-open")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(links.time, "monotonic", lambda: now[0])
    return now


def _drawn(current=False):
    screen = _Screen()
    links.draw_link_row(screen, 5, 4, ADD_ROBOT, current)
    return screen.writes


def test_a_link_never_opened_has_no_feedback(clock):
    assert links.link_feedback(ADD_ROBOT) is None
    assert len(_drawn()) == 2


def test_an_opened_link_is_tagged_opened_in_green(clock):
    links.open_link(ADD_ROBOT)
    assert links.link_feedback(ADD_ROBOT) == (" opened", _Curses().color_pair(4))


def test_the_tag_is_drawn_right_after_the_link_name(clock):
    links.open_link(ADD_ROBOT)
    label, tag = _drawn()[1:]
    assert tag[1] == label[1] + len(label[2])
    assert tag[2:] == (" opened", _Curses().color_pair(4))


def test_a_link_that_cannot_open_is_tagged_in_red(clock, monkeypatch):
    monkeypatch.delenv("DISPLAY")
    links.open_link(ADD_ROBOT)
    assert links.link_feedback(ADD_ROBOT) == (" can't open", _Curses().color_pair(2))


def test_an_os_error_counts_as_not_opened(clock, monkeypatch):
    def boom(*_a, **_k):
        raise OSError

    monkeypatch.setattr(subprocess, "Popen", boom)
    links.open_link(ADD_ROBOT)
    assert links.link_feedback(ADD_ROBOT)[0] == " can't open"


def test_the_tag_is_still_there_just_before_the_deadline(clock):
    links.open_link(ADD_ROBOT)
    clock[0] += FEEDBACK_SECONDS - 0.1
    assert links.link_feedback(ADD_ROBOT) is not None


def test_the_tag_is_gone_after_three_seconds(clock):
    links.open_link(ADD_ROBOT)
    clock[0] += FEEDBACK_SECONDS + 0.1
    assert links.link_feedback(ADD_ROBOT) is None
    assert len(_drawn()) == 2


def test_opening_again_restarts_the_clock(clock):
    links.open_link(ADD_ROBOT)
    clock[0] += 2
    links.open_link(ADD_ROBOT)
    clock[0] += 2
    assert links.link_feedback(ADD_ROBOT) is not None


def test_the_status_line_messages_are_unchanged(clock, monkeypatch):
    assert links.open_link(ADD_ROBOT) == f"Opened {ADD_ROBOT.url}"
    monkeypatch.delenv("DISPLAY")
    assert links.open_link(ADD_ROBOT) == f"Open in a browser: {ADD_ROBOT.url}"
