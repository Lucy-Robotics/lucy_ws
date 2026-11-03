"""Launcher state, package status tracking, and UI helpers."""

import os
import threading
import time

from .constants import LOADING_TIMEOUT, STOPPING_TIMEOUT
from .config import get_dev_mode, load_state
from .package import Package, _pkg_visible
from .shell import tmux_window_snapshot


_pkg_start_times = {}  # pkg_id -> float, timestamp when start was issued
_intended_running = set()  # pkg_ids that should be running (for crash detection)
_pkg_stop_times = {}  # pkg_id -> float, timestamp when an async stop was issued


class LauncherState:
    def __init__(self, config_data):
        running_state = load_state()
        dev_mode = get_dev_mode()
        package_configs = [
            p for p in config_data["packages"] if _pkg_visible(p, dev_mode)
        ]
        self.packages = [
            Package(p, running_state["modifiers"]) for p in package_configs
        ]
        self.package_map = {p.id: p for p in self.packages}

    def get_by_id(self, pkg_id):
        return self.package_map.get(pkg_id)

    def probe_snapshot(self):
        """Probe every package's status and return {pkg_id: status}, mutating nothing.

        Runs the shell probes without touching the packages, so StatusPoller can
        call it off the UI thread."""
        running_modifiers = load_state()["modifiers"]
        windows, dead = tmux_window_snapshot()
        return {
            pkg.id: pkg.probe_status(running_modifiers, windows, dead)
            for pkg in self.packages
        }

    def apply_snapshot(self, snapshot):
        """Write a probe_snapshot() result onto the packages. UI thread only."""
        for pkg in self.packages:
            status = snapshot.get(pkg.id)
            if status is not None:
                pkg.apply_status(status)

    def refresh_status(self):
        """Re-probe running/ready state for all packages without touching selected.

        Blocks for as long as the slowest readiness check; use StatusPoller from
        anywhere that must stay responsive."""
        self.apply_snapshot(self.probe_snapshot())

    def _enable(self, pkg):
        """Tick a package, clearing anything it conflicts with first."""
        for conflict_id in pkg.conflicts:
            conflict_pkg = self.get_by_id(conflict_id)
            if conflict_pkg and conflict_pkg.selected:
                conflict_pkg.selected = False
        pkg.selected = True

    def _enable_with_deps(self, pkg):
        """Tick a package and any of its (transitive) dependencies that are off."""
        for dep_id in pkg.dependencies:
            dep = self.get_by_id(dep_id)
            if dep and not dep.selected:
                self._enable_with_deps(dep)
        self._enable(pkg)

    def _disable_with_dependents(self, pkg):
        """Untick a package and any (transitive) dependents."""
        for other_pkg in self.packages:
            if pkg.id in other_pkg.dependencies and other_pkg.selected:
                self._disable_with_dependents(other_pkg)
        pkg.selected = False

    def _robot_packages(self):
        return [p for p in self.packages if p.requires_pkg]

    def toggle(self, pkg_id):
        pkg = self.get_by_id(pkg_id)
        if not pkg:
            return None
        if pkg_id in _pkg_stop_times and not pkg.selected:
            return "Still stopping…"
        if not pkg.selected:
            self._enable_with_deps(pkg)
        else:
            if pkg.requires_pkg:
                selected_robots = [r for r in self._robot_packages() if r.selected]
                if len(selected_robots) <= 1:
                    return "One robot package required"
            self._disable_with_dependents(pkg)
        return None


class StatusPoller:
    """Runs the package status probes on a background thread.

    Readiness checks are arbitrary shell out of launcher_config.json, and core's
    ends in `ros2 control list_controllers` behind a Pixi activation — seconds
    when the stack is healthy, up to the probe's own timeout when
    controller_manager is down. Driving them from the curses loop freezes it for
    that long, so a keystroke lands only once the slowest probe has returned.
    The thread here only ever produces snapshots and the UI thread applies them,
    which also keeps Package fields single-writer.
    """

    def __init__(self, state, interval=5.0):
        self._state = state
        self._interval = interval
        self._snapshot = None
        self._generation = 0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_interval(self, seconds):
        """Seconds to wait between probe passes, or None to idle until asked."""
        self._interval = seconds

    def request_refresh(self):
        """Probe again now, discarding any pass already in flight.

        Called after applying changes: a snapshot taken before the change
        describes the old world and would undo the optimistic state
        apply_changes() just set."""
        with self._lock:
            self._generation += 1
            self._snapshot = None
        self._wake.set()

    def take(self):
        """Pop the newest snapshot, or None if none has landed since the last take."""
        with self._lock:
            snapshot, self._snapshot = self._snapshot, None
        return snapshot

    def stop(self):
        self._stopped.set()
        self._wake.set()

    def _run(self):
        while not self._stopped.is_set():
            with self._lock:
                generation = self._generation
            try:
                snapshot = self._state.probe_snapshot()
            except Exception:
                snapshot = None
            if snapshot is not None:
                with self._lock:
                    if generation == self._generation:
                        self._snapshot = snapshot
            # Wait after a pass, never during one: a probe that outruns the
            # interval spaces itself out instead of stacking up another pass.
            self._wake.wait(self._interval)
            self._wake.clear()


def get_pkg_status(pkg):
    """Return one of: running, loading, crashed, stopped, stopping."""
    if pkg.id in _pkg_stop_times:
        if not pkg.is_running:
            _pkg_stop_times.pop(pkg.id, None)
            return "stopped"
        if time.time() - _pkg_stop_times[pkg.id] < STOPPING_TIMEOUT:
            return "stopping"
        _pkg_stop_times.pop(pkg.id, None)
    if pkg.pane_dead:
        _pkg_start_times.pop(pkg.id, None)
        if pkg.pane_exit_status == 0:
            _intended_running.discard(pkg.id)
            return "stopped"
        return "crashed"
    if pkg.ready:
        _pkg_start_times.pop(pkg.id, None)
        return "running"
    if pkg.id in _intended_running:
        if not pkg.is_running:
            _pkg_start_times.pop(pkg.id, None)
            return "crashed"
        timeout = getattr(pkg, "readiness_timeout", LOADING_TIMEOUT)
        started = _pkg_start_times.get(pkg.id)
        if started is None:
            _pkg_start_times[pkg.id] = time.time()
            return "loading"
        if time.time() - started < timeout:
            return "loading"
        return "crashed"
    return "stopped"


def _has_unapplied_changes(state):
    for pkg in state.packages:
        if pkg.id in _pkg_start_times or pkg.id in _pkg_stop_times:
            continue
        if pkg.selected != pkg.is_running:
            return True
    return False


def _nav_hint(pkg):
    """Navigation hint for packages without a web URL (e.g. tmux terminal windows)."""
    if not pkg.nav_hint or not pkg.is_running:
        return ""
    return f"({pkg.nav_hint})"


def _crash_hint(pkg, status):
    """The failure next to CRASHED. Anything else is still in progress or done."""
    if status != "crashed":
        return ""
    message = getattr(pkg, "crash_message", "") or ""
    return " ".join(message.split())


def _stage_hint(pkg, status):
    """Readiness progress for a package, e.g. "6/8 Building robot model...".

    LOADING on its own says nothing about whether a 150-second core bringup is
    seconds from ready or wedged on its first milestone, so the row names the
    milestone the probe is waiting on and how far through the list it is.

    Shown only while loading: a stage reads as progress, and next to STOPPED or
    CRASHED it would instead look like something still on its way."""
    stage = getattr(pkg, "stage", None)
    if status != "loading" or not stage:
        return ""
    return f"{stage['index']}/{stage['total']} {stage['label']}..."


def _status_url(pkg):
    """Expanded access URL for a package, or '' if unset env vars leave it unresolved."""
    if not pkg.url:
        return ""
    expanded = os.path.expandvars(pkg.url)
    if "${" in expanded or expanded.endswith(":"):
        return ""
    return expanded
