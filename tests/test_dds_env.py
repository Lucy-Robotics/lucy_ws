"""Tests for the DDS discovery scope exported before every ros2 call.

Two entry points set the same scope: scripts/dds_env.sh for the shell path and
apply_dds_scope() in scripts/pixi_lucy_launch.py, which is what Windows runs.
Both are covered here; the shell half skips where there is no bash.
"""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dds_env.sh"

posix_only = pytest.mark.skipif(
    os.name == "nt",
    reason="dds_env.sh needs bash and env; Windows scopes discovery in pixi_lucy_launch.py",
)


def _launcher_module():
    spec = importlib.util.spec_from_file_location(
        "pixi_lucy_launch", ROOT / "scripts" / "pixi_lucy_launch.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope(monkeypatch, windows=False, **overrides):
    """Run apply_dds_scope() with a clean slate plus overrides; return its exports."""
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    _launcher_module().apply_dds_scope(windows=windows)
    return {
        "range": os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE", ""),
        "peers": os.environ.get("ROS_STATIC_PEERS", ""),
        "localhost_only": os.environ.get("ROS_LOCALHOST_ONLY", ""),
        "cyclone": os.environ.get("CYCLONEDDS_URI", ""),
    }

PROBE = (
    "source scripts/dds_env.sh; "
    "echo \"range=${ROS_AUTOMATIC_DISCOVERY_RANGE-}\"; "
    "echo \"peers=${ROS_STATIC_PEERS-}\"; "
    "echo \"localhost_only=${ROS_LOCALHOST_ONLY-}\"; "
    "echo \"cyclone=${CYCLONEDDS_URI:+set}\""
)

CLEARED = ("CYCLONEDDS_URI", "LUCY_DDS_LOCALHOST", "LUCY_DDS_PEERS",
           "LUCY_DDS_RANGE", "LUCY_DDS_INTERFACE", "ROS_STATIC_PEERS",
           "ROS_AUTOMATIC_DISCOVERY_RANGE", "ROS_LOCALHOST_ONLY")


def _source(**overrides):
    """Source dds_env.sh with a clean slate plus overrides; return its exports."""
    cmd = ["env"] + [f"-u{name}" for name in CLEARED]
    cmd += [f"{k}={v}" for k, v in overrides.items()]
    cmd += ["bash", "-c", PROBE]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in out.strip().splitlines())


@posix_only
def test_discovery_is_scoped_to_localhost_by_default():
    assert _source()["range"] == "LOCALHOST"


@posix_only
def test_static_peers_are_additive_to_localhost():
    got = _source(LUCY_DDS_PEERS="hostA, hostB")
    assert got["peers"] == "hostA;hostB", "rcl splits ROS_STATIC_PEERS on ';'"
    assert got["range"] == "LOCALHOST"


@posix_only
def test_subnet_discovery_remains_available():
    assert _source(LUCY_DDS_LOCALHOST="0")["range"] == "SUBNET"


@posix_only
@pytest.mark.parametrize("value", ["OFF", "SUBNET", "SYSTEM_DEFAULT"])
def test_range_can_be_set_verbatim(value):
    assert _source(LUCY_DDS_RANGE=value)["range"] == value


@posix_only
def test_localhost_only_is_never_set():
    # Deprecated, and it takes precedence over the range set here.
    for overrides in ({}, {"LUCY_DDS_LOCALHOST": "0"}, {"LUCY_DDS_PEERS": "hostA"}):
        assert _source(**overrides)["localhost_only"] == ""


def test_python_entry_scopes_to_localhost_by_default(monkeypatch):
    assert _scope(monkeypatch)["range"] == "LOCALHOST"


def test_windows_keeps_the_loopback_pin_instead_of_the_localhost_range(monkeypatch):
    got = _scope(monkeypatch, windows=True, CYCLONEDDS_URI="<loopback/>")
    assert got["range"] == "SUBNET", "rmw_cyclonedds's LOCALHOST mode discovers nothing on Windows"
    assert got["cyclone"] == "<loopback/>"


def test_windows_subnet_drops_the_loopback_pin(monkeypatch):
    got = _scope(monkeypatch, windows=True, CYCLONEDDS_URI="<loopback/>", LUCY_DDS_LOCALHOST="0")
    assert got["range"] == "SUBNET"
    assert got["cyclone"] == ""


def test_windows_pins_cyclone_to_loopback_for_every_pixi_process():
    pixi = (ROOT / "pixi.toml").read_text()
    windows = pixi[pixi.index("[target.win.activation]"):]
    windows = windows[:windows.index("\n[", 1)]
    assert 'RMW_IMPLEMENTATION = "rmw_cyclonedds_cpp"' in windows
    assert '<NetworkInterface address="127.0.0.1" multicast="true"/>' in windows


def test_python_entry_keeps_peers_additive(monkeypatch):
    got = _scope(monkeypatch, LUCY_DDS_PEERS="hostA, hostB")
    assert got["peers"] == "hostA;hostB"
    assert got["range"] == "LOCALHOST"


def test_python_entry_allows_subnet(monkeypatch):
    assert _scope(monkeypatch, LUCY_DDS_LOCALHOST="0")["range"] == "SUBNET"


@pytest.mark.parametrize("value", ["OFF", "SUBNET", "SYSTEM_DEFAULT"])
def test_python_entry_sets_range_verbatim(monkeypatch, value):
    assert _scope(monkeypatch, LUCY_DDS_RANGE=value)["range"] == value


def test_python_entry_never_sets_localhost_only(monkeypatch):
    for overrides in ({}, {"LUCY_DDS_LOCALHOST": "0"}, {"LUCY_DDS_PEERS": "hostA"}):
        assert _scope(monkeypatch, **overrides)["localhost_only"] == ""


def test_both_entry_points_agree_on_the_default():
    """The shell and Python paths must not drift apart."""
    assert 'ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST"' in SCRIPT.read_text()
    source = (ROOT / "scripts" / "pixi_lucy_launch.py").read_text()
    assert '"ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"' in source
    assert 'os.environ["ROS_LOCALHOST_ONLY"] =' not in source, (
        "deprecated, and setting it makes rcl ignore the range"
    )


@posix_only
def test_explicit_cyclone_config_is_left_alone():
    cmd = ["env"] + [f"-u{n}" for n in CLEARED if n != "CYCLONEDDS_URI"]
    cmd += ["CYCLONEDDS_URI=<CycloneDDS/>", "bash", "-c",
            "source scripts/dds_env.sh; echo \"$CYCLONEDDS_URI\""]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert out.strip() == "<CycloneDDS/>"


def test_script_is_sourced_before_every_ros_command():
    shell = (ROOT / "launcher" / "shell.py").read_text()
    assert "_env_prelude" in shell and "_dds_source()" in shell
    assert "DDS_ENV_SCRIPT" in shell, "the prelude must source this script"
    assert "dds_env.sh" in (ROOT / "launcher" / "constants.py").read_text()
    assert "dds_env.sh" in (ROOT / "scripts" / "controllers_active.sh").read_text()
