#!/usr/bin/env python3
"""escort_state_bridge_node — escort/patrol/dock 상태를 관찰해 web에 push.

publish:
    /escort_state (alfred_interfaces/msg/RobotState)

State sequence (1F→2F cross-floor escort):
    PATROL → ESCORT_1F → WAITING_1F → ESCORT_1F_FINISHED
    → ESCORT_2F → ESCORT_2F_FINISHED → ESCORT_COMPLETED → PATROL

Dock/charge cycle (patrol_node 배터리 저하 시):
    PATROL → DOCKING → UNDOCKING → PATROL
"""
from __future__ import annotations

from datetime import datetime, timezone

import rclpy
from geometry_msgs.msg import Pose2D
from rclpy.node import Node
from std_msgs.msg import String

from alfred_driving.locations import LOCATIONS
from alfred_interfaces.msg import RobotState

_HANDOFF_WAIT_SEC = 3.0

# ── 상태 상수 ─────────────────────────────────────────────────────────────────
PATROL              = "PATROL"
ESCORT_1F           = "ESCORT_1F"
WAITING_1F          = "WAITING_1F"
ESCORT_1F_FINISHED  = "ESCORT_1F_FINISHED"
ESCORT_2F           = "ESCORT_2F"
ESCORT_2F_FINISHED  = "ESCORT_2F_FINISHED"
ESCORT_COMPLETED    = "ESCORT_COMPLETED"
DOCKING             = "DOCKING"
UNDOCKING           = "UNDOCKING"


class EscortStateBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('escort_state_bridge_node')

        self.pub_state = self.create_publisher(RobotState, '/escort_state', 10)

        for robot in ('robot2', 'robot4'):
            self.create_subscription(
                String, f'/{robot}/nav_status',
                lambda msg, r=robot: self._on_nav_status(msg, r),
                10,
            )
        self.create_subscription(String, '/escort_request', self._on_request, 10)

        # 내부 추적 변수
        self.state: str = PATROL
        self.pending_request: str | None = None
        self.escort_robot: str | None = None
        self.continue_robot: str | None = None
        self.arrived: dict[str, bool] = {}
        self.escort_stage: str | None = None
        self.continue_stage: str | None = None
        self.wait_timer = None
        self._dock_robot: str | None = None  # 현재 도킹 중인 로봇

        self._publish_state()
        self.get_logger().info("escort_state_bridge_node 시작 — /escort_state 로 변경 시 발행")

    # ── 요청 콜백 ─────────────────────────────────────────────────────────────

    def _on_request(self, msg: String) -> None:
        goal_name = msg.data.strip()
        if goal_name not in LOCATIONS:
            return
        if self.state != PATROL or self.pending_request is not None:
            return
        self.pending_request = goal_name

    # ── nav_status 콜백 ───────────────────────────────────────────────────────

    def _on_nav_status(self, msg: String, robot: str) -> None:
        data = msg.data

        # ── 도킹/언도킹 (배터리 충전 전용, 에스코트 중이 아닐 때만) ──────────
        if data == 'docking' and self.state == PATROL:
            self._dock_robot = robot
            self._set_state(DOCKING)
            return

        if data == 'undocking' and self.state in (DOCKING, PATROL):
            self._set_state(UNDOCKING)
            return

        if data == 'patrol_resumed' and self.state == UNDOCKING:
            self._dock_robot = None
            self._set_state(PATROL)
            return

        # ── 에스코트 시작 (robot2 순찰 중단) ─────────────────────────────────
        if robot == 'robot2' and data.startswith('patrol_stopped'):
            goal_name = self.pending_request
            if ':' in data:
                goal_name = data.split(':', 1)[1].strip()
            if goal_name is None or goal_name not in LOCATIONS:
                return
            self.pending_request = None
            self._start_escort(goal_name)
            return

        # ── arrived 처리 ──────────────────────────────────────────────────────
        if data != 'arrived':
            return

        if self.state == ESCORT_1F and robot in self.arrived:
            self.arrived[robot] = True
            if all(self.arrived.values()):
                self._set_state(WAITING_1F)
                self.wait_timer = self.create_timer(_HANDOFF_WAIT_SEC, self._on_wait_complete)

        elif self.state in (ESCORT_2F, ESCORT_2F_FINISHED):
            if robot == self.escort_robot and self.escort_stage == "TO_HOME":
                self.escort_stage = "DONE"
                self._try_finish()
            elif robot == self.continue_robot:
                if self.continue_stage == "TO_GOAL":
                    # robot4가 목적지 도착 → 2F 안내 완료
                    self.continue_stage = "TO_HOME"
                    self._set_state(ESCORT_2F_FINISHED)
                elif self.continue_stage == "TO_HOME":
                    self.continue_stage = "DONE"
                    self._try_finish()

    # ── 에스코트 상태 전이 ────────────────────────────────────────────────────

    def _start_escort(self, goal_name: str) -> None:
        goal = LOCATIONS[goal_name]
        if goal["robot"] == "robot2":
            # 같은 층 이동 — escort_node가 IDLE 유지, 여기서도 상태 변경 없음
            return

        self.escort_robot = "robot2"
        self.continue_robot = goal["robot"]  # robot4
        self.arrived = {self.escort_robot: False, self.continue_robot: False}
        self.escort_stage = None
        self.continue_stage = None
        self._set_state(ESCORT_1F)

    def _on_wait_complete(self) -> None:
        """WAITING_1F 대기 종료 → robot4가 2F 안내 시작."""
        self.wait_timer.cancel()
        self.wait_timer = None
        self.escort_stage = "TO_HOME"
        self.continue_stage = "TO_GOAL"
        self._set_state(ESCORT_1F_FINISHED)
        self._set_state(ESCORT_2F)

    def _try_finish(self) -> None:
        if self.escort_stage == "DONE" and self.continue_stage == "DONE":
            self._reset()

    def _reset(self) -> None:
        self.escort_robot = None
        self.continue_robot = None
        self.arrived = {}
        self.escort_stage = None
        self.continue_stage = None
        self._set_state(ESCORT_COMPLETED)
        self._set_state(PATROL)

    # ── 발행 ──────────────────────────────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        if new_state == self.state:
            return
        old = self.state
        self.state = new_state
        self.get_logger().info(f"[escort_state] {old} → {new_state}")
        self._publish_state()

    def _publish_state(self) -> None:
        if self.escort_robot and self.continue_robot:
            task_id = f"{self.escort_robot}->{self.continue_robot}"
        elif self._dock_robot:
            task_id = self._dock_robot
        else:
            task_id = ""

        msg = RobotState()
        msg.robot_id = "escort"
        msg.state = self.state
        msg.pose = Pose2D(x=0.0, y=0.0, theta=0.0)
        msg.battery = 0
        msg.current_task_id = task_id
        msg.task_status = ""
        msg.error_code = ""
        msg.timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.pub_state.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EscortStateBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
