#!/usr/bin/env python3
"""wake_turn_to_person 离线测试，不依赖 ROS 2 或真机。"""

import math
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_robot_agent import ROS2Interface, SmartRobotAgent


class WakeTurnToPersonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.interface = ROS2Interface.__new__(ROS2Interface)
        self.interface.set_four_combine_motor_control = AsyncMock()

    async def test_radian_angle_is_forwarded_to_yaw(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": True,
            "result": 101,
            "task_id": 123456,
        }

        result = await self.interface.wake_turn_to_person(0.7854, 2)

        self.assertEqual(
            result,
            {"type": "wake_turn_to_person", "success": True, "error_msg": ""},
        )
        self.interface.set_four_combine_motor_control.assert_awaited_once_with(
            control_yaw=True,
            yaw_angle=0.7854,
            speed_level=2,
        )

    async def test_255_uses_default_45_degrees(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": True,
            "result": 101,
        }

        await self.interface.wake_turn_to_person(255)

        kwargs = self.interface.set_four_combine_motor_control.await_args.kwargs
        self.assertAlmostEqual(kwargs["yaw_angle"], math.pi / 4, places=6)
        self.assertEqual(kwargs["speed_level"], 2)

    async def test_motor_failure_is_propagated(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": False,
            "error_msg": "四联电机拒绝执行",
        }

        result = await self.interface.wake_turn_to_person(math.pi / 2, 1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_msg"], "四联电机拒绝执行")

    async def test_invalid_angle_is_rejected_without_motor_command(self):
        for angle in (-0.1, 2 * math.pi + 0.1, "not-a-number", float("nan"), True):
            with self.subTest(angle=angle):
                self.interface.set_four_combine_motor_control.reset_mock()
                result = await self.interface.wake_turn_to_person(angle, 2)
                self.assertFalse(result["success"])
                self.interface.set_four_combine_motor_control.assert_not_awaited()

    async def test_invalid_speed_is_rejected(self):
        for speed in (-1, 3, 1.5, "fast", True):
            with self.subTest(speed=speed):
                self.interface.set_four_combine_motor_control.reset_mock()
                result = await self.interface.wake_turn_to_person(0.5, speed)
                self.assertFalse(result["success"])
                self.interface.set_four_combine_motor_control.assert_not_awaited()


class WakeTurnDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_dispatches_upper_protocol(self):
        agent = SmartRobotAgent.__new__(SmartRobotAgent)
        agent.ros2_interface = MagicMock()
        agent._wake_turn_completed_at = False
        agent._wake_turn_angle = 0.0
        agent._wake_turn_context_lock = threading.Lock()
        agent.ros2_interface.wake_turn_to_person = AsyncMock(return_value={
            "type": "wake_turn_to_person",
            "success": True,
            "error_msg": "",
        })

        result = await agent._execute_task_by_type(
            "wake_turn_to_person",
            {"angle": 0.7854, "turn_speed": 2},
        )

        agent.ros2_interface.wake_turn_to_person.assert_awaited_once_with(
            angle=0.7854,
            turn_speed=2,
        )
        self.assertEqual(
            result,
            {"type": "wake_turn_to_person", "success": True, "error_msg": ""},
        )
        self.assertTrue(agent._wake_turn_completed_at)
        self.assertAlmostEqual(agent._wake_turn_angle, 0.7854)


if __name__ == "__main__":
    unittest.main(verbosity=2)
