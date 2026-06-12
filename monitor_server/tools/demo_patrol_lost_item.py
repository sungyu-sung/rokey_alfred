#!/usr/bin/env python3
"""Run a patrol-then-lost-item demo against the local monitor DB.

This is for the local SQLite dashboard path only:
  - updates latest_robot_status so /api/robots and /viz move the robot marker
  - appends robot_status_log entries so the path/history is visible
  - inserts a LOST_ITEM event so the alarm beacon appears on /viz

Usage:
  cd /home/kimi/alfred_ws/monitor_server
  python3 tools/demo_patrol_lost_item.py
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import db  # noqa: E402
import event_service  # noqa: E402
from robot_registry import RobotRegistry  # noqa: E402


PATROL_WAYPOINTS = [
    (-7.0, 2.7),
    (-7.0, 1.3),
    (-2.7, 2.12),
    (-2.7, 3.3),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def heading(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def make_payload(
    robot_id: str,
    x: float,
    y: float,
    theta: float,
    state: str,
    task_status: str,
    battery: int,
) -> dict:
    floor = config.ROBOTS.get(robot_id, {}).get("floor")
    return {
        "robot_id": robot_id,
        "state": state,
        "pose": {"x": x, "y": y, "theta": theta},
        "battery": battery,
        "current_task_id": "patrol_demo",
        "task_status": task_status,
        "error_code": None,
        "timestamp": utc_now_iso(),
        "floor": floor,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Patrol demo with LOST_ITEM discovery")
    parser.add_argument("--robot-id", default="robot2")
    parser.add_argument("--step-delay", type=float, default=1.2,
                        help="Seconds between patrol updates")
    parser.add_argument("--post-event-hold", type=float, default=12.0,
                        help="Seconds to keep the demo visible after the event")
    parser.add_argument("--battery-start", type=int, default=86)
    parser.add_argument("--battery-drop", type=int, default=1)
    parser.add_argument("--snapshot-ref", default="patrol_lost_item_demo.jpg")
    parser.add_argument("--clear-demo-event", action="store_true",
                        help="Resolve old LOST_ITEM demo rows for this robot before starting")
    args = parser.parse_args()

    db.init_db()
    registry = RobotRegistry()
    robot_id = args.robot_id

    if args.clear_demo_event:
        rows = db.query_all(
            "SELECT id FROM events WHERE robot_id=? AND event_type='LOST_ITEM' AND resolved=0",
            (robot_id,),
        )
        for row in rows:
            db.execute(
                "UPDATE events SET resolved=1, resolved_at=?, resolved_by=? WHERE id=?",
                (utc_now_iso(), "demo_cleanup", row["id"]),
            )

    print(f"[demo] starting patrol demo for {robot_id} on floor {config.ROBOTS.get(robot_id, {}).get('floor')}")

    battery = args.battery_start
    waypoints = PATROL_WAYPOINTS
    for i, (x, y) in enumerate(waypoints):
        nxt = waypoints[(i + 1) % len(waypoints)]
        theta = heading((x, y), nxt)
        payload = make_payload(
            robot_id=robot_id,
            x=x,
            y=y,
            theta=theta,
            state="PATROL",
            task_status=f"PATROL_STEP_{i + 1}",
            battery=battery,
        )
        registry.update_from_status(payload)
        print(f"[demo] patrol step {i + 1}: x={x:.2f} y={y:.2f} theta={theta:.2f}")
        time.sleep(args.step_delay)
        battery = max(0, battery - args.battery_drop)

        if i == 1:
            lost_payload = {
                "msg_id": f"demo-{int(time.time())}",
                "event_type": "LOST_ITEM",
                "class": "lost_item",
                "robot_id": robot_id,
                "confidence": 0.96,
                "location": {"x": x, "y": y, "floor": config.ROBOTS.get(robot_id, {}).get("floor")},
                "snapshot_ref": args.snapshot_ref,
                "timestamp": utc_now_iso(),
            }
            event_service.record_event(lost_payload)
            registry.update_from_status(make_payload(
                robot_id=robot_id,
                x=x,
                y=y,
                theta=theta,
                state="PATROL",
                task_status="LOST_ITEM_FOUND",
                battery=battery,
            ))
            print(f"[demo] LOST_ITEM detected at x={x:.2f} y={y:.2f}")
            time.sleep(args.step_delay)

    if args.post_event_hold > 0:
        print(f"[demo] holding for {args.post_event_hold:.1f}s so the alarm remains visible")
        time.sleep(args.post_event_hold)

    print("[demo] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
