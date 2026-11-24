import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import install  # noqa: E402
from macos import warm_up  # noqa: E402


def make_installed(root, *packages):
    for package in packages:
        (root / "install" / package).mkdir(parents=True)


def test_installed_robot_prefers_so101_then_falls_back_to_what_is_installed(tmp_path):
    assert warm_up.installed_robot(tmp_path) is None
    make_installed(tmp_path, "inmoov_urdf")
    assert warm_up.installed_robot(tmp_path) == "inmoov_urdf"
    make_installed(tmp_path, "so_arm101_urdf")
    assert warm_up.installed_robot(tmp_path) == "so_arm101_urdf"


def test_warm_up_runs_on_its_own_domain_port_and_ready_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "0")
    env = warm_up.warm_up_environment(tmp_path / "ready", 45678)
    assert env["ROS_DOMAIN_ID"] == warm_up.WARM_UP_DOMAIN_ID != "0"
    assert env["PORT_ROSBRIDGE"] == "45678"
    assert env["LUCY_CONTROL_READY_FILE"] == str(tmp_path / "ready")
    assert env["LUCY_TMUX_SESSION"] != install.os.environ.get("LUCY_TMUX_SESSION", "lucy_ws_0")


def test_mock_launch_command_never_drives_hardware():
    assert "mode:=mock" in warm_up.mock_launch_command("inmoov_urdf")


class FakeProcess:
    def __init__(self, exits_after=None):
        self.polls = 0
        self.exits_after = exits_after

    def poll(self):
        self.polls += 1
        return 1 if self.exits_after is not None and self.polls > self.exits_after else None


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def nap(self, seconds):
        self.now += seconds


def test_wait_until_ready_returns_once_the_supervisor_writes_the_ready_file(tmp_path):
    clock = FakeClock()
    ready = tmp_path / "ready"

    def nap(seconds):
        clock.nap(seconds)
        if clock.now >= 3:
            ready.write_text("123 2")

    assert warm_up.wait_until_ready(FakeProcess(), ready, 60, clock, nap)
    assert clock.now == 3


def test_wait_until_ready_gives_up_when_the_launch_exits(tmp_path):
    clock = FakeClock()
    assert not warm_up.wait_until_ready(FakeProcess(exits_after=2), tmp_path / "ready", 60, clock, clock.nap)
    assert clock.now == 2


def test_wait_until_ready_gives_up_at_the_timeout(tmp_path):
    clock = FakeClock()
    assert not warm_up.wait_until_ready(FakeProcess(), tmp_path / "ready", 5, clock, clock.nap)
    assert clock.now == 5


def test_main_skips_without_a_robot_package(tmp_path, monkeypatch):
    monkeypatch.setattr(warm_up.subprocess, "Popen", lambda *a, **k: pytest.fail("launched"))
    assert warm_up.main(tmp_path) == 0


@pytest.fixture
def commands(monkeypatch):
    recorded = []
    monkeypatch.delenv("LUCY_SKIP_WARM_UP", raising=False)
    return recorded, lambda command, check=True, cwd=None: recorded.append((command, check)) or 0


def test_macos_install_warms_up_without_failing_the_install(monkeypatch, commands):
    recorded, run = commands
    monkeypatch.setattr(install.sys, "platform", "darwin")
    install.warm_up_macos_first_launch("/ws", run, lambda _m: None)
    assert recorded == [(["pixi", "run", "python", "scripts/macos/warm_up.py"], False)]


def test_warm_up_is_skipped_off_macos_and_when_opted_out(monkeypatch, commands):
    recorded, run = commands
    monkeypatch.setattr(install.sys, "platform", "linux")
    install.warm_up_macos_first_launch("/ws", run, lambda _m: None)
    monkeypatch.setattr(install.sys, "platform", "darwin")
    monkeypatch.setenv("LUCY_SKIP_WARM_UP", "1")
    install.warm_up_macos_first_launch("/ws", run, lambda _m: None)
    assert recorded == []


def test_build_warms_up_after_the_panel_build(monkeypatch):
    order = []
    monkeypatch.setattr(install, "ensure_macos_linker", lambda *a, **k: None)
    monkeypatch.setattr(install, "setup_firmware_toolchain", lambda *a, **k: None)
    monkeypatch.setattr(install, "build_local_realsense_optional", lambda *a, **k: None)
    monkeypatch.setattr(install, "pixi_run", lambda _root, args, _run: order.append(args[-1]) or 0)
    monkeypatch.setattr(install, "warm_up_macos_first_launch", lambda *a, **k: order.append("warm-up"))
    install.build_workspace("/ws", lambda *a, **k: 0, lambda _m: None)
    assert order[-2:] == ["panel-build", "warm-up"]
