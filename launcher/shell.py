"""Shell command execution, Pixi wrapping, and async runners."""

import os
import shlex
import subprocess
import threading

from .constants import (
    DDS_ENV_SCRIPT,
    GUI_ENV_KEYS,
    NIX_GL_ENV_SCRIPT,
    TMUX_SESSION,
    WORKSPACE_ROOT,
)
from .process import _schedule_orphan_cleanup
from .tmux import HOST_TMUX


def _gui_env_exports() -> str:
    parts = []
    for key in GUI_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            parts.append(f"export {key}={shlex.quote(val)}")
    return "; ".join(parts)


def _nix_gl_source() -> str:
    """Source hook for host GL (Jetson Tegra / NixOS Mesa) before Pixi conda GL."""
    if os.environ.get("LUCY_NIX_GL", "auto").lower() in ("0", "false", "no", "off"):
        return ""
    if not NIX_GL_ENV_SCRIPT.is_file():
        return ""
    return f"source {shlex.quote(str(NIX_GL_ENV_SCRIPT))}; "


def _dds_source() -> str:
    """Source hook for DDS discovery: localhost-only unicast where multicast is
    blocked (macOS Local Network permission), configurable via .env."""
    if not DDS_ENV_SCRIPT.is_file():
        return ""
    return f"source {shlex.quote(str(DDS_ENV_SCRIPT))}; "


def _env_prelude() -> str:
    """Env fixups sourced inside `pixi run`, immediately before the command.

    Sourced in the innermost shell so the exports reach the launched process."""
    return _dds_source() + _nix_gl_source()


def _pixi_workspace_script(user_cmd: str) -> str:
    """Shell script body: workspace root + Pixi env (RoboStack + colcon overlay).

    The inner shell is deliberately NOT a login shell. On macOS /etc/profile runs
    path_helper, which rebuilds PATH with /usr/local/bin and friends in front, so
    a login shell demotes the Pixi env below whatever Python is installed system
    wide. Anything with a `#!/usr/bin/env python3` shebang — rosbridge_websocket
    among them — then runs under that interpreter instead of Pixi's, and rclpy's
    compiled extension is built for exactly one CPython minor version:

        _rclpy_pybind11.cpython-312-darwin.so

    Under any other version the import fails with "No module named
    'rclpy._rclpy_pybind11'". It only appears to work when the system Python
    happens to match Pixi's. `bash -c` keeps Pixi's PATH ordering intact."""
    user_cmd = user_cmd.strip()
    prelude = _env_prelude()
    if user_cmd.startswith("pixi "):
        pixi_part = user_cmd
    elif prelude or any(op in user_cmd for op in (";", "&&", "||", "|", "&")):
        pixi_part = f"pixi run -- bash -c {shlex.quote(prelude + user_cmd)}"
    elif user_cmd.startswith("ros2 "):
        pixi_part = f"pixi run -- bash -c {shlex.quote(prelude + user_cmd)}"
    else:
        pixi_part = f"pixi run -- {user_cmd}"
    body = f"cd {WORKSPACE_ROOT} && {pixi_part}"
    exports = _gui_env_exports()
    if exports:
        body = f"{exports}; {body}"
    return body


def _tmux_new_pixi_window(
    window: str, user_cmd: str, remain_on_exit: bool = False
) -> str:
    """Open a tmux window that runs user_cmd inside pixi run (tmux panes don't inherit pixi)."""
    inner = f"bash -lc {shlex.quote(_pixi_workspace_script(user_cmd))}"
    cmd = f"{HOST_TMUX} new-window -d -t {TMUX_SESSION} -n {window} {inner}"
    if remain_on_exit:
        cmd += (
            f"; {HOST_TMUX} set-window-option -t {TMUX_SESSION}:{window} remain-on-exit on"
        )
    return cmd


def _complex_package_start(pkg) -> str:
    """Legacy complex {start,stop,is_running} entries — route through Pixi when possible."""
    if pkg.id == "control_panel":
        return _tmux_new_pixi_window(
            "control_panel", "pixi run panel-dev", remain_on_exit=True
        )
    return pkg.command["start"]


def run_shell_command(cmd, capture_output=False):
    if capture_output:
        return (
            subprocess.run(cmd, shell=True, capture_output=True, text=True).returncode
            == 0
        )
    subprocess.run(cmd, shell=True)


def run_shell_command_async(cmd, *, schedule_cleanup=False):
    """Fire a shell command without blocking the UI (daemon thread reaps the child).

    Used for stops so the TUI can show STOPPING while a slow shutdown runs.
    When schedule_cleanup is True, a debounced orphan cleanup runs afterward."""

    def _target():
        try:
            if cmd:
                subprocess.run(cmd, shell=True, check=False)
        except Exception:
            pass
        if schedule_cleanup:
            _schedule_orphan_cleanup()

    threading.Thread(target=_target, daemon=True).start()


def run_teardown_async(teardown_fn):
    """Run a tmux stop callable without blocking the UI; debounced orphan cleanup after."""

    def _target():
        try:
            teardown_fn()
        finally:
            _schedule_orphan_cleanup()

    threading.Thread(target=_target, daemon=True).start()


def tmux_window_snapshot():
    """Live window names and {window: exit status of its dead pane}.

    One query for all packages; asking per package cost a shell, a tmux client
    and a grep each.
    """
    out = subprocess.run(
        f"{HOST_TMUX} list-panes -s -t {TMUX_SESSION} "
        "-F '#{window_name}:#{pane_dead}:#{pane_dead_status}' 2>/dev/null",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout
    windows = set()
    dead = {}
    for line in out.splitlines():
        parts = line.strip().split(":")
        if len(parts) < 2:
            continue
        name, is_dead, status = parts[0], parts[1], parts[2] if len(parts) > 2 else ""
        windows.add(name)
        if is_dead == "1" and name not in dead:
            try:
                dead[name] = int(status)
            except ValueError:
                dead[name] = -1  # signal death reports no status; treat as a crash
    return windows, dead


def _pane_exit_status(pkg_id):
    """Exit code of the package's dead tmux pane, or None if it isn't dead.
    remain-on-exit keeps the dead pane (and its output) so we can read the code:
    0 is a clean exit (STOPPED), anything else (incl. signal death) a crash (CRASHED)."""
    out = subprocess.run(
        f"{HOST_TMUX} list-panes -t {TMUX_SESSION}:{pkg_id} "
        f"-F '#{{pane_dead}}:#{{pane_dead_status}}' 2>/dev/null",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout
    for line in out.splitlines():
        dead, _, status = line.strip().partition(":")
        if dead == "1":
            try:
                return int(status)
            except ValueError:
                return -1  # signal death reports no status; treat as a crash
    return None
