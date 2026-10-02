"""Package model and visibility helpers."""

import os
import subprocess

from .constants import LOADING_TIMEOUT, WORKSPACE_ROOT
from .config import save_state
from .shell import run_shell_command, _pane_exit_status
from .tmux import HOST_TMUX


def _env_enabled(var_name):
    """True when a package has no env gate, or its `requires_env` var is truthy."""
    if not var_name:
        return True
    return os.environ.get(var_name, "").strip().lower() in ("1", "true", "yes")


def _ros_pkg_installed(pkg_name):
    """True when a ROS package is built in the workspace overlay (install/<pkg>)."""
    if not pkg_name:
        return True
    return (WORKSPACE_ROOT / "install" / pkg_name).is_dir()


def _readiness_stages(raw):
    """Ordered (label, check) readiness milestones from config.

    A package may split its readiness probe into named stages instead of one
    opaque `readiness_check`, so the TUI can say which milestone the stack is
    still waiting on rather than only that it is LOADING. Malformed entries are
    dropped: launcher_config.json is hand-edited, and a typo in one stage must
    not take the whole probe (and with it the package's status) down."""
    stages = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        label, check = entry.get("label"), entry.get("check")
        if label and check:
            stages.append((str(label), str(check)))
    return stages


def _pkg_visible(pkg_config, dev_mode):
    """Whether a package appears in the launcher."""
    if pkg_config.get("dev_only") and not dev_mode:
        return False
    if not _ros_pkg_installed(pkg_config.get("requires_pkg")):
        return False
    return _env_enabled(pkg_config.get("requires_env"))


class Package:
    def __init__(self, data, running_modifiers):
        self.id = data["id"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.type = data["type"]
        self.dependencies = data.get("dependencies", [])
        self.conflicts = data.get("conflicts", [])
        self.command = data.get("command", "")
        self.lifecycle_hooks = data.get("lifecycle_hooks", {})
        self.selected = data.get("default_on", False)
        self.requires_pkg = data.get("requires_pkg")
        self.subitem = data.get("subitem", False)
        self.readiness_check = data.get("readiness_check")
        self.exit_check = data.get("exit_check")
        self.preflight_check = data.get("preflight_check")
        self.readiness_stages = _readiness_stages(data.get("readiness_stages"))
        self.readiness_timeout = data.get("readiness_timeout", LOADING_TIMEOUT)
        self.runs_on_vnc = data.get("runs_on_vnc", False)
        self.display_switch = data.get("display_switch", False)
        self.url = data.get("url")
        self.nav_hint = data.get("nav_hint", "")

        self.is_running = False
        self.ready = False
        self.stage = None
        self.pane_dead = False
        self.pane_exit_status = None
        self.update_running_status(running_modifiers)

        if self.type == "modifier" and self.requires_pkg:
            self.selected = self.is_running
        else:
            from .state import _pkg_stop_times

            if self.is_running and self.id not in _pkg_stop_times:
                self.selected = True

    def probe_status(self, running_modifiers, tmux_windows=None, tmux_dead=None):
        """Shell-probe running/ready/pane state and return it, mutating nothing.

        Every subprocess a status refresh needs lives here, and none of the
        package's own fields are written, so this is safe to run on a background
        thread while the UI keeps drawing. `readiness_check` is arbitrary shell
        from the config and can take seconds (core's ends in a `ros2 control
        list_controllers` behind a Pixi activation), which is exactly why the
        probing is separated from applying the result."""
        is_running = self.is_running
        if self.is_complex_command():
            is_running = run_shell_command(
                self.command["is_running"], capture_output=True
            )
        elif self.type == "modifier":
            is_running = self.id in running_modifiers
        elif self.type in ("core", "tool", "interface"):
            if tmux_windows is not None:
                is_running = self.id in tmux_windows
            else:
                is_running = run_shell_command(
                    f"{HOST_TMUX} list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'",
                    capture_output=True,
                )

        stage = None
        if not is_running:
            ready = False
        elif self.readiness_stages:
            ready, stage = self._probe_stages()
        elif self.readiness_check:
            ready = run_shell_command(self.readiness_check, capture_output=True)
        else:
            ready = True

        if not is_running:
            exit_status = None
        elif self.exit_check:
            res = subprocess.run(
                self.exit_check, shell=True, capture_output=True, text=True
            ).stdout.strip()
            exit_status = (
                int(res)
                if (res.isdigit() or (res.startswith("-") and res[1:].isdigit()))
                else None
            )
        elif tmux_dead is not None:
            exit_status = tmux_dead.get(self.id)
        else:
            exit_status = _pane_exit_status(self.id)
        return {
            "is_running": is_running,
            "ready": ready,
            "stage": stage,
            "pane_exit_status": exit_status,
            "pane_dead": exit_status is not None,
        }

    def _probe_stages(self):
        """Walk `readiness_stages` in order, returning (ready, stage-in-progress).

        The walk stops at the first stage that has not passed yet: that stage is
        what the stack is currently waiting on, and it is also what the package
        reports as unready. Short-circuiting is what keeps this no more expensive
        than the single `&&` chain it replaces — the costly probes sit late in
        the list precisely because nothing reaches them until the cheap ones
        pass."""
        for index, (label, check) in enumerate(self.readiness_stages):
            if not run_shell_command(check, capture_output=True):
                return False, {
                    "index": index + 1,
                    "total": len(self.readiness_stages),
                    "label": label,
                }
        return True, None

    def apply_status(self, status):
        """Write a probe_status() result onto the package. UI thread only, so
        that probe results and the optimistic updates apply_changes() makes have
        a single writer."""
        if self.type == "core" and not status["is_running"]:
            save_state({"modifiers": []})
        self.is_running = status["is_running"]
        self.ready = status["ready"]
        self.stage = status.get("stage")
        self.pane_exit_status = status["pane_exit_status"]
        self.pane_dead = status["pane_dead"]

    def update_running_status(self, running_modifiers):
        self.apply_status(self.probe_status(running_modifiers))

    def is_complex_command(self):
        return isinstance(self.command, dict)
