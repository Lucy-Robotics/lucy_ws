"""Keep one Control Center, and one stack, per host.

Two launchers can each apply changes with no idea the other exists, and that is
what produces two stacks sharing a ROS graph: two latched /robot_description
publishers, and two controller_managers over the same joints.

A launcher restarting on top of its own running stack is fine and supported --
launch_lucy.sh reuses the session for it and Package.__init__ ticks whatever is
running, so the TUI adopts the stack. Only a live second launcher is refused.

Collaborators are injectable so the decision logic is testable without processes
or a terminal.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from .constants import LAUNCHER_PIDFILE, TMUX_SESSION
from .process import (
    _iter_processes,
    _kill_process_tree,
    find_lucy_orphan_pids,
)
from .tmux import host_tmux_argv

# Set to 0/false to launch anyway; set FORCE to stop a running stack unattended.
ALLOW_MULTIPLE_ENV = "LUCY_ALLOW_MULTIPLE_STACKS"
FORCE_STOP_ENV = "LUCY_FORCE_SINGLE_STACK"

STOP_WAIT_S = 30.0


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _cmdline_of(pid: int) -> str:
    for other, cmdline in _iter_processes():
        if other == pid:
            return cmdline
    return ""


def another_launcher_pid():
    """PID of a Control Center already running here, or None.

    A pidfile, not a command-line scan: the launcher is the one process the
    orphan matcher deliberately never matches. Re-checked against the process
    table so a stale pidfile cannot lock the workspace out.
    """
    try:
        pid = int(LAUNCHER_PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid() or not _pid_alive(pid):
        return None
    cmdline = _cmdline_of(pid)
    if cmdline and "launcher" not in cmdline and "Lucy.py" not in cmdline:
        return None  # pid reused by something else
    return pid


def claim_launcher_pidfile() -> None:
    try:
        LAUNCHER_PIDFILE.write_text(str(os.getpid()))
    except OSError:
        pass


def release_launcher_pidfile() -> None:
    try:
        if int(LAUNCHER_PIDFILE.read_text().strip()) == os.getpid():
            LAUNCHER_PIDFILE.unlink()
    except (OSError, ValueError):
        pass


def _parent_pid(pid: int):
    if sys.platform == "win32":
        return None
    out = subprocess.run(
        ["ps", "-o", "ppid=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def _ancestor_pids() -> set:
    """This process and every process that launched it.

    The sweep matches command lines, and the shell that started the launcher can
    carry the workspace path and a stack marker in its own argv.
    """
    seen = set()
    pid = os.getpid()
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        pid = _parent_pid(pid)
    return seen


def running_stack_processes(exclude_pids=None):
    """(pid, cmdline) for stack processes already running on this host."""
    exclude = _ancestor_pids() | set(exclude_pids or ())
    pids = set(find_lucy_orphan_pids(exclude_pids=exclude))
    if not pids:
        return []
    return [(pid, cmdline) for pid, cmdline in _iter_processes() if pid in pids]


def running_stack_windows():
    """Package windows in the Lucy tmux session; the launcher's own is expected."""
    try:
        from .config import load_config

        package_ids = {p["id"] for p in load_config()["packages"]}
    except Exception:
        return []
    out = subprocess.run(
        host_tmux_argv("list-windows", "-t", TMUX_SESSION, "-F", "#{window_name}"),
        capture_output=True,
        text=True,
        check=False,
    )
    return [w for w in out.stdout.split() if w in package_ids]


def describe_running_stack(processes, windows) -> str:
    lines = ["A Lucy stack is already running on this machine:"]
    if windows:
        lines.append(f"  tmux windows : {', '.join(sorted(windows))}")
    for pid, cmdline in processes[:8]:
        lines.append(f"  pid {pid:<8} {cmdline[:88]}")
    if len(processes) > 8:
        lines.append(f"  ... and {len(processes) - 8} more process(es)")
    return "\n".join(lines)


def stop_running_stack(windows=None) -> bool:
    """Kill the stack's processes and package windows. True when nothing is left.

    Sweeps repeatedly: a process reparented to init as its parent dies is not in
    the snapshot the current pass is working from. The server `gz sim` forks
    survives a single pass.
    """
    for window in windows or []:
        subprocess.run(
            host_tmux_argv("kill-window", "-t", f"{TMUX_SESSION}:{window}"),
            capture_output=True,
            check=False,
        )
    exclude = _ancestor_pids()
    deadline = time.time() + STOP_WAIT_S
    while True:
        for pid in find_lucy_orphan_pids(exclude_pids=exclude):
            _kill_process_tree(pid)
        time.sleep(0.5)
        if not find_lucy_orphan_pids(exclude_pids=exclude):
            return True
        if time.time() >= deadline:
            return False


def _ask(question: str) -> bool:
    try:
        return input(question).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def guard_single_stack(
    *,
    find_launcher=another_launcher_pid,
    find_processes=running_stack_processes,
    find_windows=running_stack_windows,
    stop=stop_running_stack,
    ask=_ask,
    is_interactive=None,
    out=None,
) -> bool:
    """True when it is safe to launch; False when the caller must not proceed."""
    out = out or sys.stderr
    if _truthy(ALLOW_MULTIPLE_ENV):
        return True

    other = find_launcher()
    if other is not None:
        # Never killed: that would orphan the stack it owns.
        print(
            f"A Lucy Control Center is already running here (pid {other}).\n"
            f"Attach to it with:  tmux attach -t {TMUX_SESSION}\n"
            f"Set {ALLOW_MULTIPLE_ENV}=1 only if you really want a second one.",
            file=out,
        )
        return False

    processes = find_processes()
    windows = find_windows()
    if not processes and not windows:
        return True

    # No launcher owns these, so they are leftovers from a hard exit.
    print(describe_running_stack(processes, windows), file=out)
    print(
        "No Control Center owns it, so it is left over from an earlier run.", file=out
    )

    if is_interactive is None:
        is_interactive = sys.stdin.isatty()

    if not is_interactive and not _truthy(FORCE_STOP_ENV):
        # Never block an unattended run on a prompt nobody can answer.
        print(
            f"Refusing to start on top of it. Set {FORCE_STOP_ENV}=1 to stop it "
            f"automatically, or {ALLOW_MULTIPLE_ENV}=1 to launch anyway.",
            file=out,
        )
        return False

    if is_interactive and not _truthy(FORCE_STOP_ENV):
        if not ask("Stop it and continue? [y/N] "):
            print(
                "Leaving it alone; start the Control Center again to adopt it.",
                file=out,
            )
            return False

    print("Stopping the leftover stack...", file=out)
    if not stop(windows):
        leftover = find_processes()
        print(
            "Could not stop everything; still running: "
            + ", ".join(str(pid) for pid, _ in leftover),
            file=out,
        )
        return False
    print("Stopped.", file=out)
    return True
