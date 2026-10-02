"""Tmux session and window management."""

import os
import sys

from .constants import TMUX_SESSION

# Host tmux links system ncurses/libtinfo. Pixi activation puts conda libtinfo
# first on LD_LIBRARY_PATH (firmware_cargo_env.sh); that SONAME matches but the
# symbol version does not (NCURSES6_TINFO_6.4.current), so the client aborts.
# Clear only for the tmux process itself — pane payloads re-enter via pixi run.
_HOST_TMUX_ENV = ("env", "-u", "LD_LIBRARY_PATH", "-u", "DYLD_LIBRARY_PATH")
HOST_TMUX = "env -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH tmux"


def host_tmux_argv(*args: str) -> list:
    """argv for host tmux without Pixi's library path."""
    return [*_HOST_TMUX_ENV, "tmux", *args]


def is_in_tmux():
    return "TMUX" in os.environ


def needs_tmux_session():
    """tmux launcher is used on Linux/macOS; Windows runs launcher directly."""
    return sys.platform not in ("win32", "cygwin", "msys") and os.name != "nt"


def _window_teardown_shell(window: str) -> str:
    """Gracefully stop a tmux window: SIGINT, poll for the pane to go, kill-window."""
    target = f"{TMUX_SESSION}:{window}"
    return (
        f"{HOST_TMUX} send-keys -t {target} C-c 2>/dev/null; "
        "for _ in $(seq 1 8); do "
        f"{HOST_TMUX} list-panes -t {target} -F '#{{pane_dead}}' 2>/dev/null "
        "| grep -qx 0 || break; "
        "sleep 0.25; done; "
        f"{HOST_TMUX} kill-window -t {target} 2>/dev/null"
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
        f"{HOST_TMUX} send-keys -t {TMUX_SESSION}:core C-c 2>/dev/null; "
        "for _ in $(seq 1 20); do "
        "pgrep -f '[g]z sim' >/dev/null 2>&1 || pgrep -x rviz2 >/dev/null 2>&1 || break; "
        "sleep 0.25; done; "
        f"{HOST_TMUX} kill-window -t {TMUX_SESSION}:core 2>/dev/null"
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
