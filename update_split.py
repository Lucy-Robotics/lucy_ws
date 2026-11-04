from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import update_progress

SERVER = "lucy-update"
STATUS_WIDTH = 70
STATUS_HEIGHT = 15
LOG_MIN_WIDTH = 60
LOG_MIN_HEIGHT = 8
SIDE_BY_SIDE_FROM = STATUS_WIDTH + 1 + LOG_MIN_WIDTH
EXIT_FILE = "log/update_exit"
LOG_FILE = "log/update.log"
HISTORY_LINES = "200000"
CLIPBOARD_COMMANDS = ("wl-copy", "xclip -selection clipboard", "pbcopy")
ARRANGE = (f"[ #{{window_width}} -ge {SIDE_BY_SIDE_FROM} ]",
           f"select-layout -t {SERVER} main-vertical", f"select-layout -t {SERVER} main-horizontal")


def fits(cols: int, rows: int) -> bool:
    return cols >= SIDE_BY_SIDE_FROM or rows >= STATUS_HEIGHT + 1 + LOG_MIN_HEIGHT


def available() -> bool:
    return bool(shutil.which("tmux")) and fits(*shutil.get_terminal_size())


def clipboard_command() -> str | None:
    return next((command for command in CLIPBOARD_COMMANDS if shutil.which(command.split()[0])), None)


def log_script(cmd: list[str], env: dict[str, str]) -> str:
    update = shlex.join(["env", *(f"{key}={value}" for key, value in env.items()), *cmd])
    tmux = f"tmux -L {SERVER}"
    return (f"{update}; rc=$?; echo $rc > {EXIT_FILE}; echo; "
            f'{tmux} capture-pane -J -p -S - -t "$TMUX_PANE" > {LOG_FILE}; '
            f'echo "Update finished with exit code $rc. Full log: {LOG_FILE}"; '
            f'echo "Press Enter to close."; read _; {tmux} kill-server')


def _tmux(*args: str) -> int:
    env = {key: value for key, value in os.environ.items() if key != "TMUX"}
    return subprocess.run(["tmux", "-L", SERVER, *args], env=env, stderr=subprocess.DEVNULL, check=False).returncode


def _start(root, cmd: list[str], env: dict[str, str]) -> None:
    root_dir = str(Path(root).resolve())
    for stale in (EXIT_FILE, update_progress.PROGRESS_FILE):
        (Path(root) / stale).unlink(missing_ok=True)
    (Path(root) / EXIT_FILE).parent.mkdir(exist_ok=True)
    cols, rows = shutil.get_terminal_size()
    _tmux("new-session", "-d", "-s", SERVER, "-x", str(cols), "-y", str(rows), "-c", root_dir,
          sys.executable, "update_watch.py")
    _tmux("set-option", "-t", SERVER, "status", "off")
    _tmux("set-option", "-t", SERVER, "mouse", "on")
    _tmux("set-option", "-g", "history-limit", HISTORY_LINES)
    _tmux("set-option", "-s", "set-clipboard", "on")
    if clipboard_command():
        _tmux("set-option", "-s", "copy-command", clipboard_command())
    _tmux("set-window-option", "-t", SERVER, "main-pane-width", str(STATUS_WIDTH))
    _tmux("set-window-option", "-t", SERVER, "main-pane-height", str(STATUS_HEIGHT))
    _tmux("split-window", "-t", SERVER, "-c", root_dir, "sh", "-c", log_script(cmd, env))
    arrange = "if-shell " + " ".join(shlex.quote(part) for part in ARRANGE)
    _tmux("set-hook", "-t", SERVER, "window-resized", arrange)
    _tmux("if-shell", "-t", SERVER, *ARRANGE)


def run(root, cmd: list[str], env: dict[str, str]) -> None:
    if _tmux("has-session", "-t", f"={SERVER}") != 0:
        _start(root, cmd, env)
    _tmux("attach-session", "-t", f"={SERVER}")
