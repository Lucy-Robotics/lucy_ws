import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import install  # noqa: E402
from macos import linker as macos_linker  # noqa: E402

SDK = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX27.2.sdk"


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setattr(install.sys, "platform", "darwin")
    monkeypatch.setattr(macos_linker, "active_sdk", lambda: SDK)
    monkeypatch.setattr(macos_linker, "command_line_tools_installed", lambda: True)
    for name in ("CI", "LUCY_XCODE_SELECT_AUTO"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def linker_results(monkeypatch, results):
    values = iter(results)
    monkeypatch.setattr(macos_linker, "pixi_links_c", lambda _root: next(values))


def recorder():
    commands = []
    return commands, lambda command, check=True, cwd=None: commands.append(command) or 0


def test_readable_sdk_runs_nothing(mac):
    linker_results(mac, [True])
    commands, run = recorder()
    install.ensure_macos_linker("/ws", run, lambda _m: None)
    assert commands == []


def test_unreadable_sdk_switches_to_command_line_tools_when_accepted(mac):
    linker_results(mac, [False, True])
    mac.setenv("LUCY_XCODE_SELECT_AUTO", "1")
    commands, run = recorder()
    install.ensure_macos_linker("/ws", run, lambda _m: None)
    assert commands == [["sudo", "xcode-select", "-s", macos_linker.COMMAND_LINE_TOOLS_DIR]]


def test_unreadable_sdk_declined_stops_with_the_sdk_and_fix_named(mac):
    linker_results(mac, [False])
    mac.setattr(install, "confirm_install", lambda *a, **k: False)
    commands, run = recorder()
    with pytest.raises(install.PrerequisiteError) as error:
        install.ensure_macos_linker("/ws", run, lambda _m: None)
    assert commands == []
    assert SDK in str(error.value) and "xcode-select -s" in str(error.value)


def test_command_line_tools_still_unreadable_stops_the_install(mac):
    linker_results(mac, [False, False])
    mac.setenv("LUCY_XCODE_SELECT_AUTO", "1")
    _commands, run = recorder()
    with pytest.raises(install.PrerequisiteError):
        install.ensure_macos_linker("/ws", run, lambda _m: None)


def test_missing_command_line_tools_skips_the_switch(mac):
    linker_results(mac, [False])
    mac.setattr(macos_linker, "command_line_tools_installed", lambda: False)
    commands, run = recorder()
    with pytest.raises(install.PrerequisiteError):
        install.ensure_macos_linker("/ws", run, lambda _m: None)
    assert commands == []


def test_linux_skips_the_probe(monkeypatch):
    monkeypatch.setattr(install.sys, "platform", "linux")
    monkeypatch.setattr(macos_linker, "pixi_links_c", lambda _root: pytest.fail("probed on Linux"))
    install.ensure_macos_linker("/ws", lambda *a, **k: 0, lambda _m: None)


def test_build_checks_the_linker_before_the_firmware_toolchain(monkeypatch):
    order = []
    monkeypatch.setattr(install, "ensure_macos_linker", lambda *a, **k: order.append("linker"))
    monkeypatch.setattr(install, "setup_firmware_toolchain", lambda *a, **k: order.append("firmware"))
    monkeypatch.setattr(install, "pixi_run", lambda *a, **k: 0)
    monkeypatch.setattr(install, "build_local_realsense_optional", lambda *a, **k: None)
    install.build_workspace("/ws", lambda *a, **k: 0, lambda _m: None)
    assert order[:2] == ["linker", "firmware"]
