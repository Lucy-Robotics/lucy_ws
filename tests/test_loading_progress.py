"""Tests for the loading-progress readout on a package row.

Core takes up to 150 seconds to come up, and [LOADING] alone says nothing about
whether it is seconds from ready or wedged on its first milestone. Splitting the
readiness probe into named stages lets the row say which milestone the stack is
waiting on, and for how long.
"""

import json
import re
import types

import pytest

from launcher import DEFAULT_CONFIG_FILE, MIN_TERM_WIDTH, Package, _stage_hint
from launcher import tui


STAGES = [
    {"label": "Starting Rosbridge", "check": "check-a"},
    {"label": "Starting config services", "check": "check-b"},
    {"label": "Activating controllers", "check": "check-c"},
]


def _core_config():
    return next(
        p
        for p in json.loads(DEFAULT_CONFIG_FILE.read_text())["packages"]
        if p["id"] == "core"
    )


def _package(monkeypatch, *, passing, running=True, stages=STAGES):
    """A staged package whose stage checks pass exactly when listed in `passing`."""
    ran = []

    def fake_shell(cmd, capture_output=False):
        ran.append(cmd)
        if cmd in ("check-a", "check-b", "check-c"):
            return cmd in passing
        return running  # the tmux window-exists probe

    monkeypatch.setattr("launcher.package.run_shell_command", fake_shell)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    pkg = Package(
        {
            "id": "core",
            "name": "Core",
            "type": "core",
            "readiness_stages": stages,
        },
        [],
    )
    ran.clear()
    pkg.update_running_status([])
    return pkg, ran




def test_stage_reports_the_milestone_being_waited_on(monkeypatch):
    pkg, _ = _package(monkeypatch, passing={"check-a"})
    assert pkg.stage == {"index": 2, "total": 3, "label": "Starting config services"}
    assert pkg.ready is False


def test_first_stage_is_reported_before_anything_has_come_up(monkeypatch):
    pkg, _ = _package(monkeypatch, passing=set())
    assert pkg.stage == {"index": 1, "total": 3, "label": "Starting Rosbridge"}


def test_all_stages_passing_is_ready_and_leaves_no_stage(monkeypatch):
    pkg, _ = _package(monkeypatch, passing={"check-a", "check-b", "check-c"})
    assert pkg.ready is True
    assert pkg.stage is None


def test_probe_stops_at_the_first_unpassed_stage(monkeypatch):
    """Short-circuiting keeps eight stages no costlier than the `&&` chain."""
    _, ran = _package(monkeypatch, passing=set())
    assert "check-b" not in ran and "check-c" not in ran


def test_a_stopped_package_reports_no_stage(monkeypatch):
    """A stage next to STOPPED would read as something still on its way."""
    pkg, ran = _package(monkeypatch, passing=set(), running=False)
    assert pkg.stage is None
    assert ran == [
        "env -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH tmux list-windows "
        "-F '#{window_name}' | grep -q '^core$'"
    ]


def test_malformed_stage_entries_are_dropped(monkeypatch):
    """launcher_config.json is hand-edited."""
    pkg, _ = _package(
        monkeypatch,
        passing=set(),
        stages=[
            "not-a-dict",
            {"label": "No check"},
            {"check": "check-a"},
            {"label": "Starting Rosbridge", "check": "check-a"},
        ],
    )
    assert pkg.readiness_stages == [("Starting Rosbridge", "check-a")]
    assert pkg.stage == {"index": 1, "total": 1, "label": "Starting Rosbridge"}


def test_a_package_without_stages_keeps_its_plain_readiness_check(monkeypatch):
    calls = []

    def fake_shell(cmd, capture_output=False):
        calls.append(cmd)
        return True

    monkeypatch.setattr("launcher.package.run_shell_command", fake_shell)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    pkg = Package(
        {
            "id": "control_panel",
            "name": "Control Panel",
            "type": "interface",
            "readiness_check": "check-port",
        },
        [],
    )
    assert pkg.ready is True
    assert pkg.stage is None
    assert "check-port" in calls




def _staged_pkg(index=1, total=5, label="Starting Rosbridge"):
    return types.SimpleNamespace(
        id="core", stage={"index": index, "total": total, "label": label}
    )


def test_stage_hint_is_numbered_out_of_the_total():
    assert _stage_hint(_staged_pkg(1, 8, "Starting Rosbridge"), "loading") == (
        "1/8 Starting Rosbridge..."
    )


@pytest.mark.parametrize("status", ["running", "stopped", "crashed", "stopping"])
def test_stage_hint_only_shows_while_loading(status):
    """Only LOADING means progress."""
    assert _stage_hint(_staged_pkg(), status) == ""


def test_stage_hint_is_empty_without_a_stage():
    assert _stage_hint(types.SimpleNamespace(id="core", stage=None), "loading") == ""




class FakeCursesError(Exception):
    pass


class FakeScreen:
    """Records addstr() calls so a row's text and attributes can be asserted."""

    def __init__(self, width=80):
        self.width = width
        self.writes = []

    def getmaxyx(self):
        return (24, self.width)

    def addstr(self, y, x, text, attr=0):
        if x + len(text) > self.width:
            raise FakeCursesError()
        self.writes.append((y, x, text, attr))


@pytest.fixture
def fake_curses(monkeypatch):
    """curses constants need a live terminal (color_pair() calls initscr)."""
    stub = types.SimpleNamespace(
        color_pair=lambda n: 1 << (n + 8),
        A_NORMAL=0,
        A_BOLD=1,
        A_DIM=2,
        error=FakeCursesError,
    )
    monkeypatch.setattr(tui, "curses", stub)
    return stub


def _row_text(screen):
    return "".join(text for _, _, text, _ in screen.writes)


def test_row_shows_the_stage_after_the_loading_label(fake_curses):
    screen = FakeScreen()
    tui._draw_pkg_row(
        screen, 3, 4, "> ", "", "[x]", "Core", 0, "loading",
        stage="1/8 Starting Rosbridge...",
    )
    assert _row_text(screen) == (
        "> [x] Core [LOADING] 1/8 Starting Rosbridge..."
    )


def test_the_stage_is_greyed_out(fake_curses):
    """Dimmed so a progress readout does not compete with the status label."""
    screen = FakeScreen()
    tui._draw_pkg_row(
        screen, 3, 4, "> ", "", "[x]", "Core", 0, "loading",
        stage="1/8 Starting Rosbridge...",
    )
    stage_write = next(w for w in screen.writes if "Rosbridge" in w[2])
    assert stage_write[3] == fake_curses.A_DIM


def test_a_row_without_a_stage_is_unchanged(fake_curses):
    screen = FakeScreen()
    tui._draw_pkg_row(screen, 3, 4, "  ", "", "[ ]", "rqt GUI", 0, "stopped")
    assert _row_text(screen) == "  [ ] rqt GUI [STOPPED]"


def test_a_long_stage_is_truncated_rather_than_dropped(fake_curses):
    """addstr past the last column raises, taking the rest of the row with it."""
    screen = FakeScreen(width=50)
    tui._draw_pkg_row(
        screen, 3, 4, "> ", "", "[x]", "Core", 0, "loading",
        stage="6/8 Building robot model...",
    )
    text = _row_text(screen)
    assert text.startswith("> [x] Core [LOADING] 6/8 B")
    assert len(text) + 4 <= 50


def test_the_trailing_dots_are_dropped_before_the_label_is_cut():
    """The "n/N" already says it is in progress, so the dots go first."""
    assert tui._fit(" 1/8 Starting Rosbridge...", 26) == " 1/8 Starting Rosbridge..."
    assert tui._fit(" 1/8 Starting Rosbridge...", 23) == " 1/8 Starting Rosbridge"
    assert tui._fit(" 1/8 Starting Rosbridge...", 18) == " 1/8 Starting R..."


def test_a_cut_label_never_doubles_the_marker():
    for room in range(6, 30):
        assert "...." not in tui._fit(" 6/8 Building robot model...", room)


def test_the_cut_marker_is_ascii():
    """No setlocale(), so addstr encodes against ASCII and an ellipsis raises
    UnicodeEncodeError, which is not a curses.error and so is not caught."""
    for room in range(1, 40):
        tui._fit(" 6/8 Building robot model...", room).encode("ascii")


def test_every_core_stage_keeps_its_counter_at_the_minimum_width():
    """At MIN_TERM_WIDTH the stage gets ~25 columns, so labels are cut. The
    "n/N" and the verb may not be, or the row stops reading as progress."""
    core = _core_config()
    base = len("  [x] ") + len(core["name"]) + len(" [LOADING]") + 4
    room = MIN_TERM_WIDTH - base - 1
    total = len(core["readiness_stages"])
    for index, stage in enumerate(core["readiness_stages"], start=1):
        shown = tui._fit(f" {index}/{total} {stage['label']}...", room)
        assert len(shown) <= room
        assert f"{index}/{total}" in shown
        verb = stage["label"].split()[0]
        assert verb in shown, f"{stage['label']!r} cut past recognition: {shown!r}"




def test_core_config_declares_the_stages_of_its_old_composite_probe():
    """The stages replace core's `&&` chain, so nothing it checked may be lost."""
    core = _core_config()
    assert "readiness_check" not in core, "a leftover check would shadow the stages"
    checks = [s["check"] for s in core["readiness_stages"]]
    assert all(s["label"] for s in core["readiness_stages"])
    joined = " ".join(checks)
    assert "port_open.sh ${PORT_ROSBRIDGE:-9090}" in joined
    # `[c]onfig_pipeline_node` — the bracket keeps pgrep from matching itself.
    assert "onfig_pipeline_node" in joined
    assert "controllers_active.sh" in checks[-1]


def test_no_stage_matches_a_process_name_pgrep_cannot_see():
    """`pgrep` without -f matches the kernel's `comm`, truncated to 15 chars, so
    a longer pattern silently never matches and wedges the readout."""
    for stage in _core_config()["readiness_stages"]:
        for match in re.finditer(r"pgrep\s+(-\w+)\s+(\S+)", stage["check"]):
            flags, pattern = match.groups()
            if "f" in flags:
                continue
            name = pattern.strip("'\"")
            assert len(name) <= 15, (
                f"{stage['label']!r} greps {name!r} ({len(name)} chars) without -f; "
                "pgrep can never match it"
            )


def test_the_costly_probe_is_confined_to_the_end_of_the_walk():
    """The one stage that shells out to `ros2 control`; cheap stages go first."""
    checks = [s["check"] for s in _core_config()["readiness_stages"]]
    costly = [i for i, c in enumerate(checks) if "controllers_active" in c]
    assert costly, "core no longer checks that controllers came up"
    assert costly == list(range(costly[0], len(checks))), (
        "a cheap stage sits after the costly probe"
    )


def test_repeated_controller_probes_share_one_call():
    """Two stages ask `controllers_active.sh` at different thresholds."""
    checks = [s["check"] for s in _core_config()["readiness_stages"]]
    thresholds = [c.rsplit(None, 1)[-1] for c in checks if "controllers_active" in c]
    assert len(set(thresholds)) == len(thresholds), "two stages ask the same question"
    script = (DEFAULT_CONFIG_FILE.parent.parent / "scripts" / "controllers_active.sh").read_text()
    assert "${active}" in script.split("printf")[-1], "the cache must hold the count"
