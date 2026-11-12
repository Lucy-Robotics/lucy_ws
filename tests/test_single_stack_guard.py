"""Tests for keeping one Control Center, and one stack, per host."""

import io
import sys

import pytest

from launcher import guard_single_stack
from launcher.preflight import ALLOW_MULTIPLE_ENV, FORCE_STOP_ENV, describe_running_stack

PROCS = [(4242, "/path/ros2_control_node --ros-args"), (4243, "gz sim -r world.sdf")]

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only process introspection"
)


def _guard(processes=(), windows=(), answer=True, stop_ok=True, interactive=True,
           launcher_pid=None, **kw):
    """Run the guard against injected state; returns (proceed, stopped, output)."""
    calls = {"stopped": False}

    def stop(win):
        calls["stopped"] = True
        return stop_ok

    out = io.StringIO()
    proceed = guard_single_stack(
        find_launcher=lambda: launcher_pid,
        find_processes=lambda: list(processes),
        find_windows=lambda: list(windows),
        stop=stop,
        ask=lambda _q: answer,
        is_interactive=interactive,
        out=out,
        **kw,
    )
    return proceed, calls["stopped"], out.getvalue()


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv(ALLOW_MULTIPLE_ENV, raising=False)
    monkeypatch.delenv(FORCE_STOP_ENV, raising=False)


def test_clean_host_launches_without_asking():
    proceed, stopped, out = _guard()
    assert proceed is True
    assert stopped is False
    assert out == "", "nothing to report when no stack is running"


def test_running_processes_block_the_launch_until_answered():
    proceed, stopped, _ = _guard(processes=PROCS, answer=False)
    assert proceed is False, "declining must not start a second stack"
    assert stopped is False, "declining must not kill the running stack either"


def test_confirming_stops_the_stack_and_proceeds():
    proceed, stopped, out = _guard(processes=PROCS, answer=True)
    assert stopped is True
    assert proceed is True
    assert "Stopped." in out


def test_a_package_tmux_window_alone_is_enough_to_trigger():
    # A stack mid-startup holds a window before any node is up.
    proceed, stopped, _ = _guard(windows=["core"], answer=False)
    assert proceed is False
    assert stopped is False


def test_the_prompt_names_what_is_running():
    text = describe_running_stack(PROCS, ["core", "control_panel"])
    assert "core" in text and "control_panel" in text
    assert "4242" in text and "ros2_control_node" in text


def test_failure_to_stop_does_not_let_the_launch_through():
    proceed, _, out = _guard(processes=PROCS, answer=True, stop_ok=False)
    assert proceed is False
    assert "4242" in out, "say which processes survived"


def test_non_interactive_run_refuses_rather_than_hanging():
    proceed, stopped, out = _guard(processes=PROCS, interactive=False)
    assert proceed is False
    assert stopped is False
    assert FORCE_STOP_ENV in out and ALLOW_MULTIPLE_ENV in out


def test_force_env_stops_without_a_prompt(monkeypatch):
    monkeypatch.setenv(FORCE_STOP_ENV, "1")
    # answer=None would be falsy if the guard asked, so reaching (True, True)
    # also proves it did not prompt.
    proceed, stopped, _ = _guard(processes=PROCS, interactive=False, answer=None)
    assert (proceed, stopped) == (True, True)


def test_opt_out_env_skips_the_guard_entirely(monkeypatch):
    monkeypatch.setenv(ALLOW_MULTIPLE_ENV, "1")
    proceed, stopped, out = _guard(processes=PROCS, interactive=False)
    assert proceed is True
    assert stopped is False
    assert out == ""


def test_guard_runs_before_the_tui_takes_the_terminal():
    """A curses screen would hide the question and swallow the answer."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "launcher" / "__main__.py"
    text = src.read_text()
    assert text.index("guard_single_stack()") < text.index("curses.wrapper(main)")


@posix_only
def test_the_guard_never_targets_its_own_ancestors():
    """The sweep matches command lines, and the invoking shell can carry the
    workspace path and a stack marker in its argv."""
    import os

    from launcher.preflight import _ancestor_pids

    ancestors = _ancestor_pids()
    assert os.getpid() in ancestors
    assert os.getppid() in ancestors, "the invoking shell must be off limits"


def test_running_processes_never_include_the_caller():
    from launcher.preflight import running_stack_processes

    import os

    assert os.getpid() not in {pid for pid, _ in running_stack_processes()}


def test_a_second_control_center_is_refused():
    proceed, stopped, out = _guard(launcher_pid=4321, processes=PROCS)
    assert proceed is False
    assert "4321" in out
    assert "tmux attach" in out, "point the user at the one already running"


def test_a_live_control_center_is_never_killed():
    proceed, stopped, _ = _guard(launcher_pid=4321, processes=PROCS, answer=True)
    assert stopped is False


def test_restarting_over_your_own_stack_is_not_blocked_by_the_pidfile():
    """Restarting on top of your own stack is supported; the TUI adopts it."""
    proceed, _, _ = _guard(launcher_pid=None, processes=(), windows=())
    assert proceed is True


@posix_only
def test_pidfile_ignores_a_dead_launcher(tmp_path, monkeypatch):
    from launcher import preflight

    pidfile = tmp_path / "launcher.lucy_ws_0.pid"
    pidfile.write_text("999999")  # not a live pid
    monkeypatch.setattr(preflight, "LAUNCHER_PIDFILE", pidfile)
    assert preflight.another_launcher_pid() is None


def test_pidfile_ignores_a_reused_pid(tmp_path, monkeypatch):
    import os

    from launcher import preflight

    pidfile = tmp_path / "launcher.lucy_ws_0.pid"
    pidfile.write_text(str(os.getppid()))
    monkeypatch.setattr(preflight, "LAUNCHER_PIDFILE", pidfile)
    monkeypatch.setattr(preflight, "_cmdline_of", lambda _p: "/usr/bin/some-unrelated-daemon")
    assert preflight.another_launcher_pid() is None


def test_pidfile_round_trips(tmp_path, monkeypatch):
    import os

    from launcher import preflight

    pidfile = tmp_path / "launcher.lucy_ws_0.pid"
    monkeypatch.setattr(preflight, "LAUNCHER_PIDFILE", pidfile)
    preflight.claim_launcher_pidfile()
    assert pidfile.read_text().strip() == str(os.getpid())
    preflight.release_launcher_pidfile()
    assert not pidfile.exists()


def test_launch_script_recreates_a_missing_control_center_window():
    """Package windows keep the session alive after the launcher exits, so the
    Lucy window can be gone while the session is not."""
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1] / "launch_lucy.sh").read_text()
    assert "tmux new-window" in script and "-n Lucy" in script
    assert "send-keys -t ${TMUX_SESSION}:Lucy" not in script
