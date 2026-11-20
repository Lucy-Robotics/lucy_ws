import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ci_ros_contract import LATCHED_TOPICS, SERVICES, TOPICS, TRAJECTORY_TYPE, contract_breaks


def _graph():
    topics = {name: [kind] for name, kind in TOPICS.items()}
    topics["/left_arm_controller/joint_trajectory"] = [TRAJECTORY_TYPE]
    services = {name: [kind] for name, kind in SERVICES.items()}
    latched = {name: True for name in LATCHED_TOPICS}
    return topics, services, latched


def test_matching_graph_has_no_breaks():
    assert contract_breaks(*_graph()) == []


def test_missing_service_and_wrong_topic_type_break():
    topics, services, latched = _graph()
    del services["/mesh/get"]
    topics["/lucy/active_client"] = ["std_msgs/msg/Int32"]
    breaks = contract_breaks(topics, services, latched)
    assert any("/mesh/get" in b for b in breaks)
    assert any("/lucy/active_client" in b for b in breaks)


def test_volatile_latched_topic_breaks():
    topics, services, latched = _graph()
    latched["/robot_description"] = False
    assert contract_breaks(topics, services, latched) == ["topic /robot_description is not published transient_local"]


def test_missing_or_mistyped_trajectory_topic_breaks():
    topics, services, latched = _graph()
    topics["/left_arm_controller/joint_trajectory"] = ["std_msgs/msg/String"]
    assert any("joint_trajectory" in b for b in contract_breaks(topics, services, latched))
    del topics["/left_arm_controller/joint_trajectory"]
    assert contract_breaks(topics, services, latched) == ["no /<group>_controller/joint_trajectory topic"]
