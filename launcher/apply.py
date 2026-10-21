"""Apply package selection changes and full teardown."""

import time

from .config import load_selection
from .constants import TMUX_SESSION
from .shell import run_teardown_async
from .state import (
    _intended_running,
    _pkg_start_times,
    _pkg_stop_times,
)


def _package_needs_vite_preserve(pkg) -> bool:
    """True when this package's readiness probe or command targets a Vite dev server."""
    if pkg.readiness_check and "vite" in pkg.readiness_check.lower():
        return True
    if isinstance(pkg.command, str):
        cmd = pkg.command
    elif isinstance(pkg.command, dict):
        cmd = str(pkg.command.get("start", ""))
    else:
        cmd = ""
    cl = cmd.lower()
    return "vite" in cl or "panel-dev" in cl


def _orphan_preserve_from_state(state):
    """Tmux windows and Vite protection for services that should survive a core restart."""
    windows = set()
    protect_vite = False
    for pkg in state.packages:
        if not pkg.selected or pkg.id == "core":
            continue
        if pkg.id in _pkg_stop_times:
            continue
        if not pkg.is_running:
            continue
        if pkg.type not in ("interface", "tool") and not pkg.is_complex_command():
            continue
        windows.add(pkg.id)
        if _package_needs_vite_preserve(pkg):
            protect_vite = True
    return windows, protect_vite


def stop_all_packages(state):
    """Synchronously tear down every running package and orphan-prone processes."""
    import launcher

    launcher.set_orphan_preserve_windows([], protect_vite=False)
    if state:
        state.refresh_status()
        for pkg in state.packages:
            if pkg.id == "core" or not pkg.is_running:
                continue
            if pkg.is_complex_command():
                launcher.run_shell_command(pkg.command["stop"])
            elif pkg.type in ("tool", "interface"):
                launcher._stop_tmux_window(pkg.id)
            elif pkg.type == "modifier" and "stop" in pkg.lifecycle_hooks:
                launcher.run_shell_command(pkg.lifecycle_hooks["stop"])
        core = state.get_by_id("core")
        if core and core.is_running:
            launcher._stop_core_tmux()
        launcher.save_state({"modifiers": []})
    launcher._finish_teardown()


def apply_changes(state):
    import launcher

    preserve_windows, protect_vite = _orphan_preserve_from_state(state)
    launcher.set_orphan_preserve_windows(preserve_windows, protect_vite=protect_vite)

    last_launched_window = None
    core_pkg = state.get_by_id("core")

    modifiers_changed = False
    if core_pkg and core_pkg.selected:
        selected_modifier_ids = set(
            p.id for p in state.packages if p.type == "modifier" and p.selected
        )
        running_modifier_ids = set(
            p.id for p in state.packages if p.type == "modifier" and p.is_running
        )
        if selected_modifier_ids != running_modifier_ids:
            modifiers_changed = True

    if modifiers_changed and core_pkg and core_pkg.selected:
        launcher._stop_core_tmux()
        launcher._finish_teardown(
            preserve_package_windows=frozenset(preserve_windows),
            protect_vite=protect_vite,
        )
        launcher.save_state({"modifiers": []})
        core_pkg.is_running = False
        _pkg_start_times.pop("core", None)
        _intended_running.discard("core")
        for mod in state.packages:
            if mod.type == "modifier":
                if mod.is_running and "stop" in mod.lifecycle_hooks:
                    launcher.run_shell_command(mod.lifecycle_hooks["stop"])
                mod.is_running = False
                _pkg_start_times.pop(mod.id, None)
                _intended_running.discard(mod.id)

    for pkg in state.packages:
        if not pkg.selected and pkg.is_running:
            stopping = True
            if pkg.is_complex_command():
                launcher.run_shell_command_async(
                    pkg.command["stop"], schedule_cleanup=True
                )
            elif pkg.type == "core":
                run_teardown_async(launcher._stop_core_tmux)
                launcher.save_state({"modifiers": []})
                for mod in state.packages:
                    if mod.type == "modifier":
                        _pkg_start_times.pop(mod.id, None)
                        _intended_running.discard(mod.id)
            elif pkg.type in ("tool", "interface"):
                run_teardown_async(lambda pid=pkg.id: launcher._stop_tmux_window(pid))
            elif pkg.type == "modifier" and "stop" in pkg.lifecycle_hooks:
                launcher.run_shell_command_async(
                    pkg.lifecycle_hooks["stop"], schedule_cleanup=True
                )
            else:
                stopping = False
            _pkg_start_times.pop(pkg.id, None)
            _intended_running.discard(pkg.id)
            if stopping:
                _pkg_stop_times[pkg.id] = time.time()
            else:
                pkg.is_running = False

    for pkg in state.packages:
        crashed = pkg.pane_dead and pkg.pane_exit_status != 0
        if (
            pkg.selected
            and pkg.id not in _pkg_stop_times
            and (not pkg.is_running or crashed)
        ):
            if pkg.pane_dead:
                launcher.run_shell_command(
                    f"tmux kill-window -t {TMUX_SESSION}:{pkg.id} 2>/dev/null"
                )
                pkg.pane_dead = False
                pkg.is_running = False
            if pkg.is_complex_command():
                launcher.run_shell_command(launcher._complex_package_start(pkg))
                if pkg.readiness_check:
                    launcher.run_shell_command(
                        f"tmux set-window-option -t {TMUX_SESSION}:{pkg.id} remain-on-exit on 2>/dev/null"
                    )
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
            elif pkg.type == "core":
                base_cmd = pkg.command
                selected_modifiers = [
                    p for p in state.packages if p.type == "modifier" and p.selected
                ]
                modifier_args = [p.command for p in selected_modifiers]
                modifier_ids = [p.id for p in selected_modifiers]
                full_cmd = f"{base_cmd} {' '.join(modifier_args)}"
                launcher.run_shell_command(
                    launcher._tmux_new_pixi_window(
                        "core", full_cmd, remain_on_exit=True
                    )
                )
                launcher.save_state({"modifiers": modifier_ids})
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
                for mod in selected_modifiers:
                    _pkg_start_times[mod.id] = time.time()
                    _intended_running.add(mod.id)
            elif pkg.type in ("tool", "interface"):
                if pkg.type == "interface":
                    launcher.run_shell_command(
                        launcher._tmux_new_pixi_window(
                            pkg.id, pkg.command, remain_on_exit=True
                        )
                    )
                else:
                    launcher.run_shell_command(
                        launcher._tmux_new_pixi_window(
                            pkg.id,
                            f'{pkg.command}; echo "--- Process finished, press any key to close ---"; read',
                        )
                    )
                if pkg.type == "tool":
                    last_launched_window = pkg.id
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
            pkg.is_running = True

    if last_launched_window:
        launcher.run_shell_command(
            f"tmux select-window -t {TMUX_SESSION}:{last_launched_window}"
        )


def restore_selection(state):
    """Pre-tick packages from the last applied selection (.lucy_launcher_state.json)."""
    saved = load_selection()
    if saved is None:
        return
    robots = [p for p in state.packages if p.requires_pkg]
    for pkg in state.packages:
        if pkg.requires_pkg:
            continue
        pkg.selected = pkg.id in saved
    chosen = next((p for p in robots if p.id in saved), None)
    if chosen is not None:
        for pkg in robots:
            pkg.selected = pkg is chosen


def default_robot_selection(state):
    """Auto-tick a robot-package modifier when none is selected yet."""
    core = state.get_by_id("core")
    robots = [p for p in state.packages if p.requires_pkg]
    if not robots or not (core and core.selected):
        return
    if any(p.selected for p in robots):
        return
    if len(robots) == 1:
        robots[0].selected = True
        return
    inmoov = state.get_by_id("robot_inmoov")
    if inmoov:
        inmoov.selected = True
