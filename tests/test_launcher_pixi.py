"""Tests for launcher Pixi/tmux command wrapping (no tmux or ROS required)."""

import os
import sys

import launcher
from launcher import (
    STATE_FILE,
    WORKSPACE_ROOT,
    CORE_TEARDOWN,
    _core_teardown_shell,
    _gui_env_exports,
    _pixi_workspace_script,
    _tmux_new_pixi_window,
    _window_teardown_shell,
    apply_changes,
    is_lucy_orphan,
    is_lucy_orphan_cmdline,
    load_workspace_env,
    needs_tmux_session,
    stop_all_packages,
)


def test_state_file_is_workspace_scoped():
    assert STATE_FILE == WORKSPACE_ROOT / ".lucy_launcher_modifiers.json"


def test_pixi_workspace_script_wraps_ros2():
    body = _pixi_workspace_script("ros2 doctor --report")
    assert f"cd {WORKSPACE_ROOT}" in body
    assert "pixi run -- bash -c" in body
    assert "nix_gl_env.sh" in body
    assert "ros2 doctor --report" in body


def test_pixi_workspace_script_preserves_pixi_command():
    body = _pixi_workspace_script("pixi run panel-dev")
    assert "pixi run panel-dev" in body
    assert "pixi run -- pixi" not in body


def test_pixi_workspace_script_complex_shell_uses_bash_c():
    body = _pixi_workspace_script("echo hi && ros2 doctor")
    assert "pixi run -- bash -c" in body


def test_pixi_workspace_script_inner_shell_is_not_a_login_shell():
    """A login shell runs /etc/profile -> path_helper on macOS, which puts
    /usr/local/bin ahead of the Pixi env. Anything with a `#!/usr/bin/env python3`
    shebang then runs under the system Python, and rclpy's compiled extension is
    built for one CPython minor version only, so the import fails with
    "No module named 'rclpy._rclpy_pybind11'" whenever the two disagree."""
    for cmd in ("ros2 doctor --report", "echo hi && ros2 doctor"):
        assert "bash -lc" not in _pixi_workspace_script(cmd)


def test_gui_env_exports_forwards_display():
    os.environ["DISPLAY"] = ":1"
    exports = _gui_env_exports()
    assert "export DISPLAY=" in exports
    assert ":1" in exports
    del os.environ["DISPLAY"]


def test_tmux_new_pixi_window_wraps_in_bash_lc():
    cmd = _tmux_new_pixi_window("core", "ros2 launch pkg launch.py", remain_on_exit=True)
    assert "tmux new-window" in cmd
    assert "env -u LD_LIBRARY_PATH" in cmd
    assert "-n core" in cmd
    assert "bash -lc" in cmd
    assert "remain-on-exit on" in cmd


def test_load_workspace_env_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PORT_CONTROL_PANEL=5555\n")
    monkeypatch.setattr(launcher, "WORKSPACE_ROOT", tmp_path)
    os.environ.pop("PORT_CONTROL_PANEL", None)
    load_workspace_env()
    assert os.environ.get("PORT_CONTROL_PANEL") == "5555"


def test_needs_tmux_session_false_on_windows():
    if os.name == "nt":
        assert needs_tmux_session() is False


def test_window_teardown_sends_sigint_before_kill():
    cmd = _window_teardown_shell("control_panel")
    assert "send-keys" in cmd
    assert "C-c" in cmd
    assert "kill-window" in cmd
    assert "control_panel" in cmd
    assert "sleep 0.25" in cmd


def test_core_teardown_waits_before_kill_window():
    cmd = _core_teardown_shell()
    assert "C-c" in cmd
    assert "kill-window" in cmd
    assert "pgrep" in cmd
    assert cmd == CORE_TEARDOWN


def test_is_lucy_orphan_cmdline_requires_workspace():
    ws = str(WORKSPACE_ROOT)
    assert is_lucy_orphan_cmdline(f"gz sim server {ws}/install/world.sdf")
    assert not is_lucy_orphan_cmdline("gz sim server /other/project/world.sdf")


def test_is_lucy_orphan_gz_sim_server_via_workspace_markers(monkeypatch):
    monkeypatch.setattr(launcher, "_process_workspace_markers", lambda pid: pid == 1120406)
    assert is_lucy_orphan(1120406, "gz sim server")
    assert not is_lucy_orphan(999, "gz sim server")


def test_is_lucy_orphan_gz_sim_gui_via_workspace_markers(monkeypatch):
    monkeypatch.setattr(launcher, "_process_workspace_markers", lambda _pid: True)
    assert is_lucy_orphan(1, "gz sim gui")


def test_is_lucy_orphan_cmdline_excludes_launcher():
    ws = str(WORKSPACE_ROOT)
    assert not is_lucy_orphan_cmdline(f"python {ws}/launcher.py")
    assert not is_lucy_orphan_cmdline(f"python {ws}/Lucy.py")


def test_is_lucy_orphan_skips_unrelated_processes(monkeypatch):
    marker_calls = []
    monkeypatch.setattr(
        launcher,
        "_process_workspace_markers",
        lambda pid: marker_calls.append(pid) or False,
    )
    assert not is_lucy_orphan(42, "/usr/lib/systemd/systemd --user")
    assert not is_lucy_orphan(42, "firefox")
    assert marker_calls == []


def test_is_lucy_orphan_vite_short_cmdline_via_cwd(monkeypatch):
    cp = f"{WORKSPACE_ROOT}/src/lucy_control_panel"
    monkeypatch.setattr(launcher, "_read_proc_cwd", lambda _pid: cp)
    # Workspace membership is probed per platform (/proc on Linux, PowerShell on
    # Windows), so pin it and let this test cover only the vite cwd fallback.
    monkeypatch.setattr(launcher, "_process_workspace_markers", lambda _pid: True)
    assert is_lucy_orphan(123, "node node_modules/vite/bin/vite.js")


def test_is_lucy_orphan_vite_rejects_other_app_in_workspace():
    ws = str(WORKSPACE_ROOT)
    assert not is_lucy_orphan(0, f"node {ws}/other-app/vite.js")


def test_is_lucy_orphan_cmdline_vite_scoped_to_control_panel():
    ws = str(WORKSPACE_ROOT)
    assert is_lucy_orphan_cmdline(
        f"node {ws}/src/lucy_control_panel/node_modules/vite/bin/vite.js"
    )
    assert not is_lucy_orphan_cmdline(f"node {ws}/other-app/vite.js")


def test_find_lucy_orphan_pids_preserves_control_panel_vite(monkeypatch):
    cp = f"{WORKSPACE_ROOT}/src/lucy_control_panel"
    monkeypatch.setattr(launcher, "_read_proc_cwd", lambda _pid: cp)
    monkeypatch.setattr(launcher, "_process_workspace_markers", lambda _pid: True)
    vite_pid = 999999
    vite_cmd = "node node_modules/vite/bin/vite.js"

    def fake_iter():
        yield vite_pid, vite_cmd

    monkeypatch.setattr(launcher.process, "_iter_processes", fake_iter)
    assert launcher.is_lucy_orphan(vite_pid, vite_cmd)
    assert vite_pid not in launcher.find_lucy_orphan_pids(
        preserve_package_windows=frozenset(["control_panel"]),
        protect_vite=True,
    )
    assert vite_pid in launcher.find_lucy_orphan_pids(
        preserve_package_windows=frozenset(["control_panel"]),
        protect_vite=False,
    )
    assert vite_pid in launcher.find_lucy_orphan_pids(protect_vite=False)


def test_stop_all_packages_single_finish_teardown(monkeypatch):
    finish_count = []

    class FakePkg:
        def __init__(self, pid, ptype, running):
            self.id = pid
            self.type = ptype
            self.is_running = running
            self.lifecycle_hooks = {}

        def is_complex_command(self):
            return False

    class FakeState:
        def refresh_status(self):
            pass

        def get_by_id(self, pid):
            if pid == "core":
                return FakePkg("core", "core", True)
            return None

        packages = [
            FakePkg("control_panel", "interface", True),
            FakePkg("core", "core", True),
        ]

    monkeypatch.setattr(launcher, "_stop_tmux_window", lambda _w: None)
    monkeypatch.setattr(launcher, "_stop_core_tmux", lambda: None)
    monkeypatch.setattr(
        launcher, "_finish_teardown", lambda: finish_count.append(1)
    )
    monkeypatch.setattr(launcher, "save_state", lambda _data: None)

    stop_all_packages(FakeState())
    assert finish_count == [1]


def test_stop_all_packages_always_finishes_teardown(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "_finish_teardown", lambda: calls.append("finish"))
    stop_all_packages(None)
    assert calls == ["finish"]


def test_stop_all_packages_stops_running_interfaces(monkeypatch):
    calls = []

    class FakePkg:
        def __init__(self, pid, ptype, running):
            self.id = pid
            self.type = ptype
            self.is_running = running
            self.lifecycle_hooks = {}

        def is_complex_command(self):
            return False

    class FakeState:
        def refresh_status(self):
            pass

        def get_by_id(self, _):
            return None

        packages = [
            FakePkg("control_panel", "interface", True),
            FakePkg("core", "core", False),
        ]

    monkeypatch.setattr(
        launcher, "_stop_tmux_window", lambda w: calls.append(f"window:{w}")
    )
    monkeypatch.setattr(launcher, "_finish_teardown", lambda: calls.append("finish"))
    monkeypatch.setattr(launcher, "save_state", lambda _data: calls.append("save"))

    stop_all_packages(FakeState())
    assert calls == ["window:control_panel", "save", "finish"]


def test_stop_all_packages_runs_core_teardown_when_running(monkeypatch):
    calls = []

    class FakePkg:
        def __init__(self, pid, ptype, running):
            self.id = pid
            self.type = ptype
            self.is_running = running
            self.lifecycle_hooks = {}

        def is_complex_command(self):
            return False

    class FakeCore(FakePkg):
        pass

    core = FakeCore("core", "core", True)

    class FakeState:
        def refresh_status(self):
            pass

        def get_by_id(self, pid):
            return core if pid == "core" else None

        packages = [core]

    monkeypatch.setattr(launcher, "_stop_core_tmux", lambda: calls.append("core"))
    monkeypatch.setattr(launcher, "_finish_teardown", lambda: calls.append("finish"))
    monkeypatch.setattr(launcher, "save_state", lambda _data: None)

    stop_all_packages(FakeState())
    assert calls == ["core", "finish"]


def test_stop_all_packages_skips_tmux_on_windows(monkeypatch):
    monkeypatch.setattr(launcher, "needs_tmux_session", lambda: False)
    shell_calls = []
    finish_calls = []

    monkeypatch.setattr(
        launcher, "run_shell_command", lambda cmd: shell_calls.append(cmd)
    )
    monkeypatch.setattr(
        launcher, "_finish_teardown", lambda: finish_calls.append(True)
    )

    class FakeCore:
        id = "core"
        type = "core"
        is_running = True
        lifecycle_hooks = {}

        def is_complex_command(self):
            return False

    class FakeState:
        packages = [FakeCore()]

        def refresh_status(self):
            pass

        def get_by_id(self, _):
            return FakeCore()

    stop_all_packages(FakeState())
    assert shell_calls == []
    assert len(finish_calls) >= 1


def test_apply_changes_modifier_restart_calls_finish_teardown(monkeypatch):
    """Changing modifiers while core is selected must tear down before relaunch."""
    calls = []

    class FakePkg:
        def __init__(self, pid, ptype, selected, running, command=""):
            self.id = pid
            self.type = ptype
            self.selected = selected
            self.is_running = running
            self.command = command
            self.lifecycle_hooks = {}
            self.pane_dead = False
            self.pane_exit_status = None
            self.readiness_check = None

        def is_complex_command(self):
            return False

    core = FakePkg(
        "core",
        "core",
        True,
        True,
        "ros2 launch lucy_bringup lucy.launch.py",
    )
    gazebo = FakePkg("gazebo", "modifier", True, False, "gazebo:=true")

    class FakeState:
        packages = [core, gazebo]

        def get_by_id(self, pid):
            return {"core": core, "gazebo": gazebo}.get(pid)

    monkeypatch.setattr(launcher, "_stop_core_tmux", lambda: calls.append("core_stop"))
    finish_args = []
    monkeypatch.setattr(
        launcher,
        "_finish_teardown",
        lambda preserve_package_windows=None, protect_vite=None: finish_args.append(
            (preserve_package_windows, protect_vite)
        ),
    )
    monkeypatch.setattr(launcher, "save_state", lambda _data: calls.append("save"))

    apply_changes(FakeState())
    assert calls[0] == "core_stop"
    assert "save" in calls
    assert finish_args == [(frozenset(), False)]


def test_apply_changes_modifier_restart_preserves_control_panel(monkeypatch):
    finish_args = []

    class FakePkg:
        def __init__(self, pid, ptype, selected, running, command="", readiness_check=None):
            self.id = pid
            self.type = ptype
            self.selected = selected
            self.is_running = running
            self.command = command
            self.lifecycle_hooks = {}
            self.pane_dead = False
            self.pane_exit_status = None
            self.readiness_check = readiness_check

        def is_complex_command(self):
            return False

    core = FakePkg(
        "core",
        "core",
        True,
        True,
        "ros2 launch lucy_bringup lucy.launch.py",
    )
    gazebo = FakePkg("gazebo", "modifier", True, False, "gazebo:=true")
    control_panel = FakePkg(
        "control_panel",
        "interface",
        True,
        True,
        "pixi run panel-dev",
        readiness_check="pgrep -f '[v]ite' >/dev/null 2>&1",
    )

    class FakeState:
        packages = [core, gazebo, control_panel]

        def get_by_id(self, pid):
            return {"core": core, "gazebo": gazebo, "control_panel": control_panel}.get(pid)

    monkeypatch.setattr(launcher, "_stop_core_tmux", lambda: None)
    monkeypatch.setattr(
        launcher,
        "_finish_teardown",
        lambda preserve_package_windows=None, protect_vite=None: finish_args.append(
            (preserve_package_windows, protect_vite)
        ),
    )
    monkeypatch.setattr(launcher, "save_state", lambda _data: None)
    monkeypatch.setattr(launcher, "run_shell_command", lambda _cmd: None)

    apply_changes(FakeState())
    assert finish_args == [(frozenset({"control_panel"}), True)]


def test_apply_changes_stopping_core_preserves_running_control_panel(monkeypatch):
    preserve_calls = []

    class FakePkg:
        def __init__(self, pid, ptype, selected, running, command="", readiness_check=None):
            self.id = pid
            self.type = ptype
            self.selected = selected
            self.is_running = running
            self.command = command
            self.lifecycle_hooks = {}
            self.pane_dead = False
            self.pane_exit_status = None
            self.readiness_check = readiness_check

        def is_complex_command(self):
            return False

    core = FakePkg("core", "core", False, True, "ros2 launch lucy_bringup lucy.launch.py")
    control_panel = FakePkg(
        "control_panel",
        "interface",
        True,
        True,
        "pixi run panel-dev",
        readiness_check="pgrep -f '[v]ite' >/dev/null 2>&1",
    )

    class FakeState:
        packages = [core, control_panel]

        def get_by_id(self, pid):
            return {"core": core, "control_panel": control_panel}.get(pid)

    monkeypatch.setattr(
        launcher,
        "set_orphan_preserve_windows",
        lambda windows, protect_vite=False: preserve_calls.append(
            (frozenset(windows), protect_vite)
        ),
    )
    monkeypatch.setattr(launcher, "run_teardown_async", lambda fn: fn())
    monkeypatch.setattr(launcher, "save_state", lambda _data: None)
    monkeypatch.setattr(launcher, "run_shell_command", lambda _cmd: None)

    apply_changes(FakeState())
    assert preserve_calls[0] == (frozenset({"control_panel"}), True)


def test_finish_teardown_clears_pending_preserve(monkeypatch):
    launcher.set_orphan_preserve_windows(["control_panel"], protect_vite=True)
    monkeypatch.setattr(launcher, "cleanup_lucy_orphan_processes", lambda **kwargs: None)
    monkeypatch.setattr(launcher, "wait_for_orphans_gone", lambda **kwargs: None)

    launcher._finish_teardown()
    assert launcher.process._pending_preserve_windows == frozenset()
    assert launcher.process._pending_protect_vite is False


def test_orphan_signature_covers_latching_and_locking_nodes():
    """robot_state_publisher and the controller spawner must be reaped.

    Left parented to init by a hard session kill, neither is merely idle: the
    publisher keeps a latched /robot_description alive, so the next Gazebo run can
    spawn from a stale description and gz_ros2_control fails to load its hardware
    plugins; a surviving spawner holds the ros2-control spawner lock, so every
    later spawner gives up and no controller is ever activated."""
    from launcher.process import _matches_orphan_signature

    ws = str(WORKSPACE_ROOT)
    assert _matches_orphan_signature(
        f"{ws}/.pixi/envs/default/lib/robot_state_publisher/robot_state_publisher --ros-args"
    )
    assert _matches_orphan_signature(
        f"{ws}/.pixi/envs/default/lib/controller_manager/spawner joint_state_broadcaster"
    )
    assert _matches_orphan_signature(f"{ws}/install/lucy_config_pipeline/lib/config_pipeline_node")
    # The launcher itself must never match, or it would reap its own process.
    assert not _matches_orphan_signature(f"python -m launcher")
    assert not _matches_orphan_signature(f"{ws}/Lucy.py")
    # An unrelated spawner outside ros2_control should not match on the word alone.
    assert not _matches_orphan_signature("/usr/bin/some_random_spawner --foo")


def test_core_teardown_kills_rviz_before_sigint():
    """rviz2 must be killed before the teardown SIGINT reaches it.

    Its rclcpp signal handler throws std::system_error("mutex lock failed") during
    shutdown on macOS; the exception escapes, std::terminate calls abort(), and the
    process dies on SIGABRT. macOS files that as a crash and shows "rviz2 quit
    unexpectedly" on every stop. Measured: SIGINT and SIGTERM each produce a crash
    report, SIGKILL produces none."""
    from launcher.tmux import _core_teardown_shell

    teardown = _core_teardown_shell()
    assert "pkill -9 -x rviz2" in teardown
    assert teardown.index("pkill -9 -x rviz2") < teardown.index("C-c")


def test_window_teardown_stops_waiting_once_the_pane_is_gone():
    from launcher.tmux import _window_teardown_shell

    cmd = _window_teardown_shell("control_panel")
    assert "list-panes" in cmd
    assert "break" in cmd
    assert cmd.index("C-c") < cmd.index("break") < cmd.index("kill-window")


def test_modifier_with_exit_check_reports_crash_when_exit_code_present(tmp_path):
    from launcher.package import Package
    from launcher.state import get_pkg_status, _intended_running, _pkg_start_times

    status_file = tmp_path / "bridge_status"
    pkg = Package(
        {
            "id": "real",
            "name": "... with Real Hardware",
            "type": "modifier",
            "command": "real:=true",
            "readiness_check": "false",
            "exit_check": (
                f'"{sys.executable}" -c "import pathlib, sys; '
                f'p = pathlib.Path(sys.argv[1]); '
                f'sys.stdout.write(p.read_text().strip()) if p.is_file() else None" '
                f'"{status_file}"'
            ),
        },
        running_modifiers=["real"],
    )
    # File doesn't exist yet: exit_status is None, pane_dead is False
    status = pkg.probe_status(["real"])
    assert status["pane_dead"] is False
    assert status["pane_exit_status"] is None

    # Write non-zero exit code: probe_status detects crash immediately
    status_file.write_text("1\n")
    status = pkg.probe_status(["real"])
    assert status["pane_dead"] is True
    assert status["pane_exit_status"] == 1
    pkg.apply_status(status)

    _intended_running.add("real")
    try:
        assert get_pkg_status(pkg) == "crashed"
    finally:
        _intended_running.discard("real")
        _pkg_start_times.pop("real", None)


def test_intended_running_package_crashes_immediately_when_not_running():
    import time
    from launcher.package import Package
    from launcher.state import get_pkg_status, _intended_running, _pkg_start_times

    pkg = Package(
        {
            "id": "real",
            "name": "... with Real Hardware",
            "type": "modifier",
            "command": "real:=true",
        },
        running_modifiers=[],
    )
    assert not pkg.is_running
    _intended_running.add("real")
    _pkg_start_times["real"] = time.time()
    try:
        assert get_pkg_status(pkg) == "crashed"
    finally:
        _intended_running.discard("real")
        _pkg_start_times.pop("real", None)


def test_real_hardware_stays_loading_until_microcontroller_ready_file_exists(tmp_path):
    import time
    from launcher.package import Package
    from launcher.state import get_pkg_status, _intended_running, _pkg_start_times

    ready_file = tmp_path / ".lucy_real_hardware_ready"
    pkg = Package(
        {
            "id": "real",
            "name": "... with Real Hardware",
            "type": "modifier",
            "command": "real:=true",
            "readiness_check": (
                f'"{sys.executable}" -c "import pathlib, sys; '
                f'sys.exit(0 if pathlib.Path(sys.argv[1]).is_file() else 1)" '
                f'"{ready_file}"'
            ),
            "readiness_timeout": 30,
        },
        running_modifiers=["real"],
    )

    _intended_running.add("real")
    _pkg_start_times["real"] = time.time()
    try:
        # Microcontroller has NOT been found yet: ready_file is absent
        status = pkg.probe_status(["real"])
        assert status["ready"] is False
        pkg.apply_status(status)
        assert get_pkg_status(pkg) == "loading"

        # Microcontroller found and opened: ready_file is created
        ready_file.touch()
        status = pkg.probe_status(["real"])
        assert status["ready"] is True
        pkg.apply_status(status)
        assert get_pkg_status(pkg) == "running"
    finally:
        _intended_running.discard("real")
        _pkg_start_times.pop("real", None)



