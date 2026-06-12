"""Publish a LOST_ITEM IF-05 event to the local ROS2 monitoring server.

This targets the monitor_server ingest path directly:
  /robotN/detection/info -> monitor_server/ros_ingest.py -> local DB/API -> /viz

Usage:
  source /opt/ros/humble/setup.bash && source ../install/setup.bash
  python3 tools/send_lost_item.py --robot-id robot2 --floor 1 --x -4.5 --y 2.6
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import rclpy
from std_msgs.msg import String


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a LOST_ITEM event to monitor_server")
    parser.add_argument("--robot-id", default="robot2")
    parser.add_argument("--floor", type=int, default=1)
    parser.add_argument("--x", type=float, default=-4.5)
    parser.add_argument("--y", type=float, default=2.6)
    parser.add_argument("--confidence", type=float, default=0.92)
    parser.add_argument("--snapshot-ref", default="lost_item_demo.jpg")
    args = parser.parse_args()

    rclpy.init(args=None)
    node = rclpy.create_node("send_lost_item_demo")
    pub = node.create_publisher(String, f"/{args.robot_id}/detection/info", 10)

    payload = {
        "event_type": "LOST_ITEM",
        "class": "lost_item",
        "robot_id": args.robot_id,
        "confidence": float(args.confidence),
        "location": {"x": float(args.x), "y": float(args.y), "floor": int(args.floor)},
        "snapshot_ref": args.snapshot_ref,
        "timestamp": utc_now_iso(),
    }

    msg = String()
    msg.data = json.dumps(payload, ensure_ascii=False)
    pub.publish(msg)
    node.get_logger().info(
        f"published LOST_ITEM to /{args.robot_id}/detection/info "
        f"(floor={args.floor}, x={args.x}, y={args.y})"
    )

    time.sleep(0.5)
    rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
