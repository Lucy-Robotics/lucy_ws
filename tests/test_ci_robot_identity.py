import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ci_stack
from ci_stack import Ros, check_robot_identity

URDF = '<robot name="r6bot"><link name="a"/><joint name="j1"/><mesh filename="file:///ws/inmoov_urdf/m.dae"/></robot>'


def latched_ros(description: str) -> Ros:
    ros = object.__new__(Ros)
    ros.description, ros.latest = description, {"j1": 0.0}
    return ros


def test_reset_keeps_the_latched_urdf_received_before_the_check(monkeypatch):
    monkeypatch.setattr(ci_stack, "IDENTITY_TIMEOUT_S", 1.0)
    ros = latched_ros(URDF)
    ros.reset()
    ros.latest = {"j1": 0.1}
    check_robot_identity(ros, "inmoov_urdf")
