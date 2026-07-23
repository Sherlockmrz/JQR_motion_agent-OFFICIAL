#!/usr/bin/env python3
"""forward_head 离线测试，不依赖 ROS 2 或真机。"""

import math
import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_robot_agent import HEAD_PITCH_MAX, ROS2Interface, SmartRobotAgent


class ForwardHeadTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.interface = ROS2Interface.__new__(ROS2Interface)
        self.interface.set_four_combine_motor_control = AsyncMock()

    async def test_radian_angle_is_forwarded_to_pitch(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": True,
            "result": 101,
            "task_id": 123456,
        }

        result = await self.interface.forward_head(0.2618, 2)

        self.assertEqual(
            result,
            {"type": "forward_head", "success": True, "error_msg": ""},
        )
        self.interface.set_four_combine_motor_control.assert_awaited_once_with(
            control_pitch=True,
            pitch_angle=0.2618,
            speed_level=2,
        )

    async def test_255_uses_default_15_degrees(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": True,
            "result": 101,
        }

        await self.interface.forward_head(255)

        kwargs = self.interface.set_four_combine_motor_control.await_args.kwargs
        self.assertAlmostEqual(kwargs["pitch_angle"], math.pi / 12, places=6)
        self.assertEqual(kwargs["speed_level"], 2)

    async def test_zero_and_30_degrees_are_allowed(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": True,
            "result": 101,
        }

        for angle in (0.0, HEAD_PITCH_MAX):
            with self.subTest(angle=angle):
                self.interface.set_four_combine_motor_control.reset_mock()
                result = await self.interface.forward_head(angle, 0)
                self.assertTrue(result["success"])
                self.interface.set_four_combine_motor_control.assert_awaited_once()

    async def test_motor_failure_is_propagated(self):
        self.interface.set_four_combine_motor_control.return_value = {
            "success": False,
            "error_msg": "四联电机执行失败",
        }

        result = await self.interface.forward_head(0.1, 1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_msg"], "四联电机执行失败")

    async def test_invalid_angle_is_rejected_without_motor_command(self):
        for angle in (-0.1, HEAD_PITCH_MAX + 0.01, "bad", float("inf"), True):
            with self.subTest(angle=angle):
                self.interface.set_four_combine_motor_control.reset_mock()
                result = await self.interface.forward_head(angle, 2)
                self.assertFalse(result["success"])
                self.interface.set_four_combine_motor_control.assert_not_awaited()

    async def test_invalid_speed_is_rejected(self):
        for speed in (-1, 3, 1.5, "fast", True):
            with self.subTest(speed=speed):
                self.interface.set_four_combine_motor_control.reset_mock()
                result = await self.interface.forward_head(0.1, speed)
                self.assertFalse(result["success"])
                self.interface.set_four_combine_motor_control.assert_not_awaited()


class ForwardHeadDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_dispatches_upper_protocol(self):
        agent = SmartRobotAgent.__new__(SmartRobotAgent)
        agent.ros2_interface = MagicMock()
        agent.ros2_interface.forward_head = AsyncMock(return_value={
            "type": "forward_head",
            "success": True,
            "error_msg": "",
        })

        result = await agent._execute_task_by_type(
            "forward_head",
            {"angle": 0.2618, "turn_speed": 2},
        )

        agent.ros2_interface.forward_head.assert_awaited_once_with(
            angle=0.2618,
            turn_speed=2,
        )
        self.assertEqual(
            result,
            {"type": "forward_head", "success": True, "error_msg": ""},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
