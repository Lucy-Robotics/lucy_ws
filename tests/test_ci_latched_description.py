import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ci_stack import Ros


def test_forgetting_joints_keeps_the_latched_robot_description():
    ros = Ros.__new__(Ros)
    ros.latest = {}
    ros._on_description(SimpleNamespace(data="<robot name='inmoov'/>"))
    ros._on_joints(SimpleNamespace(name=["a"], position=[0.1]))
    ros.forget_joints()
    assert ros.description == "<robot name='inmoov'/>"
    assert ros.snapshot() == {}
