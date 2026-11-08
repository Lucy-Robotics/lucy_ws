#!/usr/bin/env python3
"""Echo commanded joint positions back as JointState.

joint_trajectory_controller normally consumes <controller>/joint_trajectory and
the joint state broadcaster reports the result on /joint_states. Both live in
controller_manager, which crashes on Windows, so the control panel's commands
move nothing. Feed the commands straight back so the model follows them.

Open loop: positions are echoed as requested, with no dynamics and no hardware.
Pair with joint_state_publisher's source_list, which fills in the other joints.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory

OUTPUT_TOPIC = "/lucy/commanded_joint_states"
COMMAND_SUFFIX = "/joint_trajectory"
COMMAND_TYPE = "trajectory_msgs/msg/JointTrajectory"
PUBLISH_HZ = 30.0
DISCOVER_PERIOD_S = 2.0


class JointCommandEcho(Node):
    def __init__(self) -> None:
        super().__init__("lucy_joint_command_echo")
        self._positions: dict[str, float] = {}
        self._subscriptions_by_topic: dict = {}
        self._pub = self.create_publisher(JointState, OUTPUT_TOPIC, 10)
        self.create_timer(DISCOVER_PERIOD_S, self._discover)
        self.create_timer(1.0 / PUBLISH_HZ, self._publish)
        self._discover()

    def _discover(self) -> None:
        """Controllers come and go with the robot package, so poll for them."""
        for topic, types in self.get_topic_names_and_types():
            if topic in self._subscriptions_by_topic:
                continue
            if topic.endswith(COMMAND_SUFFIX) and COMMAND_TYPE in types:
                self._subscriptions_by_topic[topic] = self.create_subscription(
                    JointTrajectory, topic, self._on_trajectory, 10
                )
                self.get_logger().info(f"following {topic}")

    def _on_trajectory(self, msg: JointTrajectory) -> None:
        if not msg.points:
            return
        positions = msg.points[-1].positions
        for index, name in enumerate(msg.joint_names):
            if index < len(positions):
                self._positions[name] = float(positions[index])

    def _publish(self) -> None:
        if not self._positions:
            return
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(self._positions)
        msg.position = [self._positions[name] for name in msg.name]
        self._pub.publish(msg)


def main() -> None:
    rclpy.init()
    node = JointCommandEcho()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
