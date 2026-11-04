import pytest

import update_split


@pytest.mark.parametrize("cols, rows, fits", [
    (200, 15, True),
    (update_split.SIDE_BY_SIDE_FROM, 15, True),
    (80, 24, True),
    (80, 23, False),
])
def test_two_panes_need_room_on_one_side(cols, rows, fits):
    assert update_split.fits(cols, rows) is fits


def test_the_log_pane_saves_a_plain_log_before_closing():
    script = update_split.log_script(["python3", "install.py"], {"A": "b c"})
    assert script.startswith("env 'A=b c' python3 install.py; rc=$?;")
    assert script.index(update_split.EXIT_FILE) < script.index("capture-pane") < script.index("read _")
    assert script.index("read _") < script.index("kill-server")
    assert f"> {update_split.LOG_FILE}" in script


def test_layouts_switch_at_the_side_by_side_width():
    test, wide, narrow = update_split.ARRANGE
    assert str(update_split.SIDE_BY_SIDE_FROM) in test
    assert "main-vertical" in wide and "main-horizontal" in narrow


def test_the_first_available_clipboard_tool_is_used(monkeypatch):
    monkeypatch.setattr(update_split.shutil, "which", lambda name: name if name == "xclip" else None)
    assert update_split.clipboard_command() == "xclip -selection clipboard"
