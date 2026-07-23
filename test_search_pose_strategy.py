#!/usr/bin/env python3
"""wake_turn_to_person 后动态搜索归零策略的离线测试。"""

import math
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock

from smart_robot_agent import (
    DEFAULT_SEARCH_CHASSIS_ROTATION,
    SmartRobotAgent,
)


def make_agent() -> SmartRobotAgent:
    agent = SmartRobotAgent.__new__(SmartRobotAgent)
    agent.ros2_interface = MagicMock()
    agent.ros2_interface.set_four_combine_motor_control = AsyncMock(
        return_value={"success": True, "result": 101, "task_id": 123}
    )
    agent._wake_turn_completed_at = False
    agent._wake_turn_angle = 0.0
    agent._wake_turn_context_lock = threading.Lock()
    agent.send_to_local_model = AsyncMock(
        return_value={"success": True, "error_msg": ""}
    )
    return agent


class SearchPoseSelectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_wake_uses_scene_a_and_the_same_input_angle(self):
        agent = make_agent()
        agent._mark_wake_turn_context(math.pi / 2)

        result = await agent._reset_dynamic_search_pose("go_find_person")

        self.assertTrue(result["success"])
        kwargs = agent.ros2_interface.set_four_combine_motor_control.await_args.kwargs
        self.assertTrue(kwargs["control_yaw"])
        self.assertEqual(kwargs["yaw_angle"], 0.0)
        self.assertTrue(kwargs["control_roll"])
        self.assertEqual(kwargs["roll_angle"], 0.0)
        self.assertTrue(kwargs["control_pitch"])
        self.assertEqual(kwargs["pitch_angle"], 0.0)
        self.assertTrue(kwargs["control_chassis_rotate"])
        self.assertAlmostEqual(kwargs["chassis_rotation"], math.pi / 2)
        self.assertEqual(kwargs["speed_level"], 0)
        self.assertFalse(agent._wake_turn_completed_at)
        self.assertEqual(agent._wake_turn_angle, 0.0)

    async def test_default_255_wake_uses_45_degrees(self):
        agent = make_agent()
        agent._mark_wake_turn_context(255)

        await agent._reset_dynamic_search_pose("go_find_person")

        kwargs = agent.ros2_interface.set_four_combine_motor_control.await_args.kwargs
        self.assertAlmostEqual(kwargs["chassis_rotation"], math.pi / 4)

    async def test_without_wake_uses_scene_b_absolute_zero(self):
        agent = make_agent()

        await agent._reset_dynamic_search_pose("go_to_object")

        kwargs = agent.ros2_interface.set_four_combine_motor_control.await_args.kwargs
        self.assertEqual(
            kwargs["chassis_rotation"], DEFAULT_SEARCH_CHASSIS_ROTATION
        )
        self.assertEqual(kwargs["chassis_rotation"], 0.0)

    async def test_wake_does_not_expire_with_time(self):
        agent = make_agent()
        agent._wake_turn_completed_at = True
        agent._wake_turn_angle = 1.2

        await agent._reset_dynamic_search_pose("go_find_person")

        kwargs = agent.ros2_interface.set_four_combine_motor_control.await_args.kwargs
        self.assertEqual(kwargs["chassis_rotation"], 1.2)
        self.assertFalse(agent._wake_turn_completed_at)

    async def test_wake_context_is_consumed_only_once(self):
        agent = make_agent()
        agent._mark_wake_turn_context(0.9)

        await agent._reset_dynamic_search_pose("go_find_person")
        await agent._reset_dynamic_search_pose("go_to_object")

        first = agent.ros2_interface.set_four_combine_motor_control.await_args_list[0].kwargs
        second = agent.ros2_interface.set_four_combine_motor_control.await_args_list[1].kwargs
        self.assertAlmostEqual(first["chassis_rotation"], 0.9)
        self.assertEqual(second["chassis_rotation"], 0.0)

    async def test_intervening_non_search_task_does_not_clear_context(self):
        agent = make_agent()
        agent.ros2_interface.forward_head = AsyncMock(
            return_value={"type": "forward_head", "success": True, "error_msg": ""}
        )
        agent._mark_wake_turn_context(0.7)
        marked_at = agent._wake_turn_completed_at

        await agent._execute_task_by_type("forward_head", {"angle": 0.1})

        self.assertEqual(agent._wake_turn_completed_at, marked_at)

    async def test_static_find_person_does_not_consume_context(self):
        agent = make_agent()
        agent.ros2_interface.find_person = MagicMock(
            return_value={"type": "find_person", "success": True}
        )
        agent._mark_wake_turn_context(0.7)
        marked_at = agent._wake_turn_completed_at

        await agent._execute_task_by_type("find_person", {"obj_name": "张三"})

        self.assertEqual(agent._wake_turn_completed_at, marked_at)
        agent.ros2_interface.set_four_combine_motor_control.assert_not_awaited()


class DynamicSearchFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_pose_reset_is_logged_and_person_search_continues(self):
        agent = make_agent()
        agent.ros2_interface.set_four_combine_motor_control.return_value = {
            "success": False,
            "result": 103,
            "error_msg": "四联电机执行失败",
        }
        agent._mark_wake_turn_context(math.pi / 3)

        with self.assertLogs("smart_robot_agent", level="ERROR") as logs:
            result = await agent.go_find_person("张三", "去找张三")

        self.assertTrue(result["success"])
        agent.send_to_local_model.assert_awaited_once_with({
            "type": "go_to_person",
            "user_prompt": "去找张三",
            "person_id": "张三",
        })
        self.assertTrue(any(
            "场景A归零失败，但按策略继续执行go_find_person" in line
            for line in logs.output
        ))

    async def test_pose_reset_exception_is_logged_and_object_search_continues(self):
        agent = make_agent()
        agent.ros2_interface.set_four_combine_motor_control.side_effect = RuntimeError(
            "ROS2 publisher unavailable"
        )

        with self.assertLogs("smart_robot_agent", level="ERROR") as logs:
            result = await agent.go_to_object("水杯")

        self.assertTrue(result["success"])
        agent.send_to_local_model.assert_awaited_once()
        self.assertTrue(any(
            "场景B归零发生异常，但按策略继续执行go_to_object" in line
            for line in logs.output
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
