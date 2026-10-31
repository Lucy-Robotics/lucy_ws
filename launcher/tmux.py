"""Tmux session and window management."""

import os
import sys

from .constants import TMUX_SESSION


def is_in_tmux():
    return "TMUX" in os.environ


def needs_tmux_session():
    """tmux launcher is used on Linux/macOS; Windows runs launcher directly."""
    return sys.platform not in ("win32", "cygwin", "msys") and os.name != "nt"


def _window_teardown_shell(window: str) -> str:
    """Gracefully stop a tmux window: SIGINT, poll for the pane to go, kill-window."""
    target = f"{TMUX_SESSION}:{window}"
    return (
        f"tmux send-keys -t {target} C-c 2>/dev/null; "
        "for _ in $(seq 1 8); do "
        f"tmux list-panes -t {target} -F '#{{pane_dead}}' 2>/dev/null "
        "| grep -qx 0 || break; "
        "sleep 0.25; done; "
        f"tmux kill-window -t {target} 2>/dev/null"
    )


def _core_teardown_shell() -> str:
    return (
        # rviz2 has to go before the SIGINT below. Its rclcpp signal handler throws
        # std::system_error("mutex lock failed") while shutting down on macOS; the
        # exception escapes, so std::terminate calls abort() and the process dies on
        # SIGABRT. macOS files that as a crash and shows "rviz2 quit unexpectedly"
        # on every single stop. Measured on this machine: SIGINT and SIGTERM both
        # produce a crash report, SIGKILL produces none. RViz is a viewer with no
        # state to persist, so killing it outright costs nothing and is the only way
        # to stop the dialog without patching rviz2 itself.
        "pkill -9 -x rviz2 2>/dev/null; "
        f"tmux send-keys -t {TMUX_SESSION}:core C-c 2>/dev/null; "
        # Wait for ros2 launch itself too: kill-window SIGHUPs it mid-shutdown, which
        # orphans its children before the firmware can release torque.
        "for _ in $(seq 1 40); do "
        "pgrep -f '[g]z sim' >/dev/null 2>&1 || pgrep -x rviz2 >/dev/null 2>&1 || "
        f"tmux list-panes -t {TMUX_SESSION}:core -F '#{{pane_dead}}' 2>/dev/null "
        "| grep -qx 0 || break; "
        "sleep 0.25; done; "
        f"tmux kill-window -t {TMUX_SESSION}:core 2>/dev/null"
    )


# Back-compat alias for tests / docs that referenced the shell snippet.
CORE_TEARDOWN = _core_teardown_shell()


def _stop_tmux_window(window: str):
    import launcher

    if launcher.needs_tmux_session():
        launcher.run_shell_command(launcher._window_teardown_shell(window))


def _stop_core_tmux():
    import launcher

    if launcher.needs_tmux_session():
        launcher.run_shell_command(launcher._core_teardown_shell())
