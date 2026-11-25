import argparse
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.loop_timing import loop_timing_summary  # noqa: E402


def _busy(until: float) -> None:
    while time.time() < until:
        pass


def _joint_state_stamps(seconds: float, warmup: float, timeout: float) -> list:
    import rclpy
    from sensor_msgs.msg import JointState

    rclpy.init()
    node = rclpy.create_node("lucy_control_loop_probe")
    stamps = []
    node.create_subscription(
        JointState,
        "/joint_states",
        lambda m: stamps.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9),
        100,
    )
    def spin_until(done) -> None:
        while not done():
            rclpy.spin_once(node, timeout_sec=0.05)

    try:
        first_deadline = time.time() + timeout
        spin_until(lambda: stamps or time.time() > first_deadline)
        warm_end = time.time() + warmup
        spin_until(lambda: time.time() > warm_end)
        stamps.clear()
        end = time.time() + seconds
        spin_until(lambda: time.time() > end)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return stamps


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure the controller_manager loop from /joint_states stamps."
    )
    parser.add_argument("--rate", type=float, default=100.0)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--warmup", type=float, default=3.0)
    parser.add_argument("--load", type=int, default=0)
    args = parser.parse_args()

    until = time.time() + args.warmup + args.seconds + 120.0
    loaders = [multiprocessing.Process(target=_busy, args=(until,)) for _ in range(args.load)]
    for loader in loaders:
        loader.start()
    try:
        stamps = _joint_state_stamps(args.seconds, args.warmup, timeout=60.0)
    finally:
        for loader in loaders:
            loader.terminate()
    if len(stamps) < 2:
        print(f"no /joint_states on ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '0')}")
        return 1
    print(json.dumps({"load": args.load, **loop_timing_summary(stamps, args.rate)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
