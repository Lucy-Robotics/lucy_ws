"""Entry point for `python -m launcher`."""

import os
import sys

try:
    import curses
except ImportError:
    curses = None

from .config import load_config, load_workspace_env
from .constants import STATE_FILE, TMUX_SESSION, WORKSPACE_ROOT
from .apply import stop_all_packages
from .process import prune_ros_logs
from .shell import run_shell_command
from .state import LauncherState
from .preflight import claim_launcher_pidfile, guard_single_stack, release_launcher_pidfile
from .tmux import HOST_TMUX, is_in_tmux, needs_tmux_session
from .tui import main


def run():
    if sys.platform == "win32":
        # The TUI starts, stops and polls every package through tmux, and Windows
        # has no equivalent, so run the workspace through Pixi directly instead.
        print(
            "The launcher TUI is not supported on Windows yet.\n"
            "\n"
            "Run the workspace with Pixi instead:\n"
            "  pixi run core            robot stack (rosbridge on port 9090)\n"
            "  pixi run control-panel   web UI on http://localhost:4004\n"
            "  pixi run sim             stack with Gazebo\n"
            "  pixi run rviz            stack with RViz\n",
            file=sys.stderr,
        )
        sys.exit(1)
    if curses is None:
        print(
            "Error: launcher TUI requires curses (not available on this platform).",
            file=sys.stderr,
        )
        sys.exit(1)
    load_workspace_env()
    if needs_tmux_session() and not is_in_tmux():
        print(
            f"Error: launcher must run inside the {TMUX_SESSION} tmux session (./launch_lucy.sh).",
            file=sys.stderr,
        )
        sys.exit(1)
    os.chdir(WORKSPACE_ROOT)

    # Before curses takes the terminal, so the question is readable and
    # answerable on a plain prompt.
    if not guard_single_stack():
        sys.exit(1)

    claim_launcher_pidfile()
    status, state = None, None
    try:
        status, state = curses.wrapper(main)
    except KeyboardInterrupt:
        curses.endwin()
        print("\nStopping all processes and exiting workspace...")
        status = "ExitWorkspace"
        try:
            state = LauncherState(load_config())
        except Exception:
            state = None
    except Exception as e:
        curses.endwin()
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    release_launcher_pidfile()

    if status == "ExitWorkspace":
        print("\nStopping all processes and exiting workspace...")
        stop_all_packages(state)
        if STATE_FILE.is_file():
            STATE_FILE.unlink()
        pruned = prune_ros_logs()
        if pruned:
            print(f"Pruned {pruned} ros2 log entries older than a week.")
        if needs_tmux_session():
            print("Terminating tmux session...")
            run_shell_command(f"{HOST_TMUX} kill-session -t {TMUX_SESSION} 2>/dev/null")


if __name__ == "__main__":
    run()
