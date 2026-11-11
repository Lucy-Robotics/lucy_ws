"""Several Control Centers on one host: per-instance files, domains and processes."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import launcher
from launcher import config, instance, process
from launcher.constants import instance_suffix
from launcher.state import LauncherState

ROOT = Path(__file__).resolve().parents[1]


def test_default_instance_keeps_its_file_names():
    assert instance_suffix("lucy_ws") == ""
    assert instance_suffix("lucy_ws_1") == ".lucy_ws_1"


def test_pidfile_carries_the_claimed_domains(tmp_path):
    pidfile = tmp_path / ".lucy_launcher.lucy_ws_1.pid"
    instance.claim_domains({3, 1}, pidfile=pidfile)
    assert instance.read_pidfile(pidfile) == (os.getpid(), {1, 3})


def test_pidfile_without_domains_still_reads(tmp_path):
    pidfile = tmp_path / ".lucy_launcher.pid"
    pidfile.write_text("1234")
    assert instance.read_pidfile(pidfile) == (1234, set())


def test_other_instances_domains_skip_own_and_dead(tmp_path):
    alive = os.getppid()
    (tmp_path / ".lucy_launcher.pid").write_text(f"{alive}\n0\n")
    (tmp_path / ".lucy_launcher.lucy_ws_1.pid").write_text(f"{alive}\n1 4\n")
    (tmp_path / ".lucy_launcher.lucy_ws_2.pid").write_text("999999999\n2\n")  # dead
    assert instance.other_instance_domains(tmp_path, own_session="lucy_ws_3") == {0, 1, 4}
    assert instance.other_instance_domains(tmp_path, own_session="lucy_ws") == {1, 4}


def test_second_instance_gets_its_own_markers_and_gazebo_partition():
    env = {}
    instance.export_instance_env("lucy_ws_1", env)
    assert env["LUCY_TMUX_SESSION"] == "lucy_ws_1"
    assert env["GZ_PARTITION"] == "lucy_ws_1"
    assert env["LUCY_CONTROL_READY_FILE"].endswith(".lucy_ws_1")
    assert "lucy_ws_1" in env["LUCY_CLI_READY_FILE"]


def test_default_instance_keeps_stock_settings():
    env = {}
    instance.export_instance_env("lucy_ws", env)
    assert env == {"LUCY_TMUX_SESSION": "lucy_ws"}


@pytest.mark.parametrize(
    "environ, session",
    [
        ({}, "lucy_ws"),
        ({"LUCY_TMUX_SESSION": "lucy_ws_1"}, "lucy_ws_1"),
        # macOS reader: the value runs on to the next variable on the ps line.
        ({"LUCY_TMUX_SESSION": "lucy_ws_2 TERM=xterm"}, "lucy_ws_2"),
    ],
)
def test_process_session(environ, session):
    assert instance.process_session(environ) == session


def test_orphan_cleanup_leaves_other_instances_alone(monkeypatch):
    ws = launcher.LUCY_WS_MARKER
    cmdline = f"python3 {ws}/install/lib/robot_state_publisher"
    environs = {11: {}, 12: {"LUCY_TMUX_SESSION": "lucy_ws_1"}}
    monkeypatch.setattr(launcher, "_read_proc_environ", lambda pid: environs[pid])
    monkeypatch.setattr(process, "TMUX_SESSION", "lucy_ws")
    assert process.is_lucy_orphan(11, cmdline)
    assert not process.is_lucy_orphan(12, cmdline)
    monkeypatch.setattr(process, "TMUX_SESSION", "lucy_ws_1")
    assert not process.is_lucy_orphan(11, cmdline)
    assert process.is_lucy_orphan(12, cmdline)


def test_windows_receive_the_instance(monkeypatch):
    monkeypatch.setenv("LUCY_TMUX_SESSION", "lucy_ws_1")
    monkeypatch.setenv("PORT_ROSBRIDGE", "9091")
    exports = launcher._gui_env_exports()
    assert "export LUCY_TMUX_SESSION=lucy_ws_1" in exports
    assert "export PORT_ROSBRIDGE=9091" in exports


def test_dotenv_does_not_override_the_instance_ports(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PORT_ROSBRIDGE=9090\nOTHER_SETTING=1\n")
    monkeypatch.setattr(launcher, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setenv("PORT_ROSBRIDGE", "9091")
    monkeypatch.delenv("OTHER_SETTING", raising=False)
    config.load_workspace_env()
    assert os.environ["PORT_ROSBRIDGE"] == "9091"
    assert os.environ["OTHER_SETTING"] == "1"
    monkeypatch.delenv("OTHER_SETTING")


CONFIG = {"packages": [{"id": "core", "name": "Core", "type": "core", "command": "x"}]}


def _state(monkeypatch, core_running=False):
    monkeypatch.setenv("ROS_DOMAIN_ID", "0")
    monkeypatch.setattr("launcher.state.load_state", lambda: {"modifiers": []})
    monkeypatch.setattr("launcher.state.get_dev_mode", lambda: False)
    monkeypatch.setattr("launcher.package._pane_exit_status", lambda _pkg_id: None)
    state = LauncherState(CONFIG)
    state.get_by_id("core").is_running = core_running
    return state


def test_second_instance_starts_on_the_next_free_domain(monkeypatch):
    state = _state(monkeypatch)
    state.avoid_domains({0, 1})
    assert state.domain_id == 2


def test_running_core_keeps_its_domain(monkeypatch):
    state = _state(monkeypatch, core_running=True)
    state.avoid_domains({0})
    assert state.domain_id == 0


def test_counter_skips_other_instances_domains(monkeypatch):
    state = _state(monkeypatch)
    state.step_domain(1, taken={1, 2})
    assert state.domain_id == 3
    state.step_domain(-1, taken={1, 2})
    assert state.domain_id == 0
    state.step_domain(-1, taken={1, 2})
    assert state.domain_id == 0


def test_core_claims_both_domains_until_restarted(monkeypatch):
    state = _state(monkeypatch, core_running=True)
    state.step_domain(1)
    assert state.claimed_domains() == {0, 1}


@pytest.mark.skipif(sys.platform == "win32", reason="bash + pgrep")
def test_instance_pgrep_only_sees_its_instance():
    marker = f"lucy_instance_pgrep_{os.getpid()}"
    env = {**os.environ, "LUCY_TMUX_SESSION": "lucy_ws_7"}
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", marker], env=env
    )
    try:
        time.sleep(0.3)

        def pgrep(session):
            return subprocess.run(
                ["bash", str(ROOT / "scripts" / "instance_pgrep.sh"), "-f", marker],
                env={**os.environ, "LUCY_TMUX_SESSION": session},
                capture_output=True,
                text=True,
            )

        mine = pgrep("lucy_ws_7")
        assert mine.returncode == 0 and str(child.pid) in mine.stdout.split()
        assert pgrep("lucy_ws").returncode == 1
    finally:
        child.kill()
        child.wait()
