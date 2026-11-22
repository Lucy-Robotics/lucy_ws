"""scripts/pixi_lucy_launch.py reads lucy.launch.py's mode:= and domain_id:= args."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location(
        "pixi_lucy_launch", ROOT / "scripts" / "pixi_lucy_launch.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "args, sim",
    [
        (["mode:=sim", "headless:=true"], True),
        (["mode:=SIM"], True),
        (["mode:=real", "bridge:=linux"], False),
        (["rviz:=true"], False),
        (["mode:=sim", "mode:=mock"], False),
    ],
)
def test_gazebo_requested_follows_mode(launcher, args, sim):
    assert launcher.gazebo_requested(args) is sim


def test_domain_id_arg_is_exported(launcher, monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "0")
    launcher.apply_domain_id(["mode:=sim", "domain_id:=7"])
    assert launcher.os.environ["ROS_DOMAIN_ID"] == "7"


def test_no_domain_id_arg_keeps_the_environment(launcher, monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "4")
    launcher.apply_domain_id(["mode:=sim"])
    assert launcher.os.environ["ROS_DOMAIN_ID"] == "4"
