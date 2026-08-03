#!/usr/bin/env python3
"""wake_turn_to_person 离线测试，不依赖 ROS 2 或真机。"""

import math
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_robot_agent import ROS2Interface, SmartRobotAgent, plan_wake_absolute_yaw


class WakeTurnToPersonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.interface = ROS2Interface.__new__(ROS2Interface)
        self.interface.set_four_combine_waypoint_control = AsyncMock()
        self.interface._get_current_head_yaw_radians = AsyncMock(return_value=0.0)

    def assert_wake_waypoint_call(self, call, expected_yaw, expected_speed=2):
        self.assertEqual(call.kwargs["pose_mode"], 1)
        self.assertEqual(call.kwargs["timeout"], 30.0)
        self.assertEqual(len(call.kwargs["waypoints"]), 1)
        waypoint = dict(call.kwargs["waypoints"][0])
        actual_yaw = waypoint.pop("yaw_angle")
        self.assertAlmostEqual(actual_yaw, expected_yaw, places=9)
        self.assertEqual(
            waypoint,
            {
                "control_yaw": True,
                "control_roll": False,
                "roll_angle": 0.0,
                "control_pitch": False,
                "pitch_angle": 0.0,
                "control_chassis_move": False,
                "chassis_offset": 0.0,
                "control_chassis_rotate": False,
                "chassis_rotation": 0.0,
                "speed_level": expected_speed,
                "timeout": 0.0,
            },
        )

    async def test_negative_degrees_are_counterclockwise(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
            "task_id": 123456,
        }

        result = await self.interface.wake_turn_to_person(-20, 2)

        self.assertTrue(result["success"])
        self.assertEqual(result["type"], "wake_turn_to_person")
        self.assertEqual(result["error_msg"], "")
        self.assertEqual(result["_final_head_angle_degrees"], -20.0)
        self.interface.set_four_combine_waypoint_control.assert_awaited_once()
        self.assert_wake_waypoint_call(
            self.interface.set_four_combine_waypoint_control.await_args,
            math.radians(20),
        )

    async def test_positive_degrees_are_clockwise(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
        }

        await self.interface.wake_turn_to_person(105)

        call = self.interface.set_four_combine_waypoint_control.await_args
        self.assert_wake_waypoint_call(call, math.radians(-105))

    async def test_relative_command_is_limited_to_safe_absolute_target(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
        }

        await self.interface.wake_turn_to_person(-179)
        call = self.interface.set_four_combine_waypoint_control.await_args
        self.assert_wake_waypoint_call(call, math.radians(150))

        self.interface.set_four_combine_waypoint_control.reset_mock()
        await self.interface.wake_turn_to_person(180)
        call = self.interface.set_four_combine_waypoint_control.await_args
        self.assert_wake_waypoint_call(call, math.radians(-150))

    async def test_large_positive_relative_angle_is_limited_to_150(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
        }

        await self.interface.wake_turn_to_person(365)
        call = self.interface.set_four_combine_waypoint_control.await_args
        self.assert_wake_waypoint_call(call, math.radians(-150))

    async def test_each_request_is_one_independent_relative_command(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
        }

        await self.interface.wake_turn_to_person(-20)
        await self.interface.wake_turn_to_person(-15)

        calls = self.interface.set_four_combine_waypoint_control.await_args_list
        self.assertEqual(len(calls), 2)
        self.assert_wake_waypoint_call(calls[0], math.radians(20))
        self.assert_wake_waypoint_call(calls[1], math.radians(15))

    async def test_motor_failure_is_propagated(self):
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": False,
            "error_msg": "四联电机拒绝执行",
        }

        result = await self.interface.wake_turn_to_person(-90, 1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_msg"], "四联电机拒绝执行")

    async def test_invalid_angle_is_rejected_without_motor_command(self):
        for angle in ("not-a-number", float("nan"), True):
            with self.subTest(angle=angle):
                self.interface.set_four_combine_waypoint_control.reset_mock()
                result = await self.interface.wake_turn_to_person(angle, 2)
                self.assertFalse(result["success"])
                self.interface.set_four_combine_waypoint_control.assert_not_awaited()

    async def test_invalid_speed_is_rejected(self):
        for speed in (-1, 3, 1.5, "fast", True):
            with self.subTest(speed=speed):
                self.interface.set_four_combine_waypoint_control.reset_mock()
                result = await self.interface.wake_turn_to_person(-20, speed)
                self.assertFalse(result["success"])
                self.interface.set_four_combine_waypoint_control.assert_not_awaited()

    async def test_missing_position_feedback_prevents_command(self):
        self.interface._get_current_head_yaw_radians.return_value = None

        result = await self.interface.wake_turn_to_person(10, 0)

        self.assertFalse(result["success"])
        self.assertIn("四轴位置反馈", result["error_msg"])
        self.interface.set_four_combine_waypoint_control.assert_not_awaited()

    async def test_from_negative_limit_minus_150_wraps_to_positive_60(self):
        # 交互坐标-150°对应电机坐标+150°。
        self.interface._get_current_head_yaw_radians.return_value = math.radians(150)
        self.interface.set_four_combine_waypoint_control.return_value = {
            "success": True,
            "result": 101,
        }

        result = await self.interface.wake_turn_to_person(-150, 0)

        self.assertTrue(result["success"])
        call = self.interface.set_four_combine_waypoint_control.await_args
        self.assert_wake_waypoint_call(call, math.radians(-60), expected_speed=0)

    async def test_small_outward_command_at_limit_is_not_published(self):
        self.interface._get_current_head_yaw_radians.return_value = math.radians(150)

        result = await self.interface.wake_turn_to_person(-10, 0)

        self.assertFalse(result["success"])
        self.assertIn("后方禁区", result["error_msg"])
        self.interface.set_four_combine_waypoint_control.assert_not_awaited()


class WakeTargetPlanningTest(unittest.TestCase):
    def test_requested_angle_is_clamped_before_target_math(self):
        plan = plan_wake_absolute_yaw(0.0, -300.0)

        self.assertTrue(plan["valid"])
        self.assertEqual(plan["limited_relative_degrees"], -150.0)
        self.assertAlmostEqual(plan["target_interaction_degrees"], -150.0)

    def test_negative_limit_wrap_example(self):
        plan = plan_wake_absolute_yaw(math.radians(150.0), -150.0)

        self.assertTrue(plan["valid"])
        self.assertTrue(plan["wrapped"])
        self.assertAlmostEqual(plan["target_interaction_degrees"], 60.0)
        self.assertAlmostEqual(plan["target_motor_radians"], math.radians(-60.0))

    def test_back_dead_zone_is_invalid(self):
        plan = plan_wake_absolute_yaw(math.radians(150.0), -10.0)

        self.assertFalse(plan["valid"])
        self.assertAlmostEqual(plan["target_interaction_degrees"], -160.0)

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
            {"angle": -45, "turn_speed": 2},
        )

        agent.ros2_interface.wake_turn_to_person.assert_awaited_once_with(
            angle=-45,
            turn_speed=2,
        )
        self.assertEqual(
            result,
            {"type": "wake_turn_to_person", "success": True, "error_msg": ""},
        )
        self.assertTrue(agent._wake_turn_completed_at)
        self.assertAlmostEqual(agent._wake_turn_angle, math.radians(45))


if __name__ == "__main__":
    unittest.main(verbosity=2)
