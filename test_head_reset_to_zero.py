#!/usr/bin/env python3
"""head_reset_to_zero 离线测试，不依赖 ROS 2 或真机。"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_robot_agent import ROS2Interface, SmartRobotAgent


class HeadResetToZeroTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.interface = ROS2Interface.__new__(ROS2Interface)
        self.interface.set_four_combine_waypoint_control = AsyncMock()

    async def test_absolute_zero_controls_all_head_axes_only(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
        }

        result = await self.interface.head_reset_to_zero({"turn_speed": 0})

        self.assertEqual(result, {"success": True, "error_msg": ""})
        call = self.interface.set_four_combine_waypoint_control.await_args
        self.assertEqual(call.kwargs["pose_mode"], 1)
        self.assertEqual(call.kwargs["timeout"], 30.0)
        self.assertEqual(call.kwargs["waypoints"], [{
            "control_yaw": True,
            "yaw_angle": 0.0,
            "control_roll": True,
            "roll_angle": 0.0,
            "control_pitch": True,
            "pitch_angle": 0.0,
            "control_chassis_move": False,
            "chassis_offset": 0.0,
            "control_chassis_rotate": False,
            "chassis_rotation": 0.0,
            "speed_level": 0,
            "timeout": 0.0,
        }])

    async def test_failure_is_propagated(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": False,
            "error_msg": "多路点拒绝执行",
        }

        result = await self.interface.head_reset_to_zero({"turn_speed": 1})

        self.assertEqual(
            result,
            {"success": False, "error_msg": "多路点拒绝执行"},
        )

    async def test_invalid_speed_does_not_publish(self):
        for speed in (-1, 3, 1.5, "fast", True):
            with self.subTest(speed=speed):
                self.interface.set_four_combine_waypoint_control.reset_mock()
                result = await self.interface.head_reset_to_zero({"turn_speed": speed})
                self.assertFalse(result["success"])
                self.interface.set_four_combine_waypoint_control.assert_not_awaited()


class HeadResetDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_dispatches_reset_task(self):
        agent = SmartRobotAgent.__new__(SmartRobotAgent)
        agent.ros2_interface = MagicMock()
        agent.ros2_interface.head_reset_to_zero = AsyncMock(return_value={
            "success": True,
            "error_msg": "",
        })

        result = await agent._execute_task_by_type(
            "head_reset_to_zero",
            {"turn_speed": 0},
        )

        agent.ros2_interface.head_reset_to_zero.assert_awaited_once_with(
            {"turn_speed": 0}
        )
        self.assertEqual(
            result,
            {"type": "head_reset_to_zero", "success": True, "error_msg": ""},
        )


class WaypointResultTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_result_does_not_include_progress(self):
        interface = ROS2Interface.__new__(ROS2Interface)
        interface.four_combine_waypoint_result = {
            123456: {"result": 101.0},
        }

        result = await interface._wait_for_waypoint_result(123456, timeout=0.1)

        self.assertEqual(result, {"success": True, "result": 101.0})
        self.assertNotIn("progress", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
