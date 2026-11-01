#!/usr/bin/env python3

from __future__ import annotations

import re

from ci_stack import CheckFailed, Ros, log

TOPICS = {
    "/joint_states": "sensor_msgs/msg/JointState",
    "/robot_description": "std_msgs/msg/String",
    "/lucy/active_client": "std_msgs/msg/String",
    "/lucy/client_count": "std_msgs/msg/Int32",
    "/lucy/client_heartbeat": "std_msgs/msg/String",
}
LATCHED_TOPICS = ("/robot_description", "/lucy/active_client", "/lucy/client_count")
SERVICES = {
    "/lucy/control": "lucy_msgs/srv/ClientControl",
    "/lucy/get_client_count": "lucy_msgs/srv/GetInt",
    "/mesh/get": "lucy_msgs/srv/GetMesh",
}
TRAJECTORY_TOPIC = re.compile(r"^/\w+_controller/joint_trajectory$")
TRAJECTORY_TYPE = "trajectory_msgs/msg/JointTrajectory"


def contract_breaks(topics: dict[str, list[str]], services: dict[str, list[str]], latched: dict[str, bool]) -> list[str]:
    breaks = [f"topic {name} has types {topics.get(name)}, expected [{kind}]"
              for name, kind in TOPICS.items() if topics.get(name) != [kind]]
    breaks += [f"service {name} has types {services.get(name)}, expected [{kind}]"
               for name, kind in SERVICES.items() if services.get(name) != [kind]]
    breaks += [f"topic {name} is not published transient_local" for name in LATCHED_TOPICS if not latched.get(name)]
    trajectories = {name: kinds for name, kinds in topics.items() if TRAJECTORY_TOPIC.match(name)}
    if not trajectories:
        breaks.append("no /<group>_controller/joint_trajectory topic")
    breaks += [f"topic {name} has types {kinds}, expected [{TRAJECTORY_TYPE}]"
               for name, kinds in trajectories.items() if kinds != [TRAJECTORY_TYPE]]
    return breaks


def latched_publishers(ros: Ros, topic: str) -> bool:
    from rclpy.qos import DurabilityPolicy

    infos = ros.node.get_publishers_info_by_topic(topic)
    return bool(infos) and all(i.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL for i in infos)


def check_ros_contract(ros: Ros) -> None:
    topics = dict(ros.node.get_topic_names_and_types())
    services = dict(ros.node.get_service_names_and_types())
    latched = {topic: latched_publishers(ros, topic) for topic in LATCHED_TOPICS}
    breaks = contract_breaks(topics, services, latched)
    if breaks:
        raise CheckFailed("ROS interface contract broken: " + "; ".join(breaks))
    log(f"ROS interface contract holds ({len(TOPICS)} topics, {len(SERVICES)} services, trajectory topics typed)")
