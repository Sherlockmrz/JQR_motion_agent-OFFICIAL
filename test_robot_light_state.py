#!/usr/bin/env python3
"""机器状态灯 Motion Agent pipeline 离线测试，不依赖 ROS 2 或真机。"""

import unittest
from unittest.mock import MagicMock

from smart_robot_agent import ROS2Interface, SmartRobotAgent


class RobotLightStateTest(unittest.TestCase):
    def setUp(self):
        # 绕过 ROS2Interface.__init__，只测试协议映射和响应转换。
        self.interface = ROS2Interface.__new__(ROS2Interface)
        self.interface._call_ros2_service_async = MagicMock()

    def test_working_maps_to_scene_2(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"accepted": True, "message": "OK"},
        }

        result = self.interface.set_robot_light_state("1", verify=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["type"], "set_robot_light_state")
        self.assertEqual(result["scene"], 2)
        self.assertEqual(result["ambient"], 0)
        self.assertFalse(result["verified"])
        self.interface._call_ros2_service_async.assert_called_once_with(
            "/set_status_light_scene",
            1,
            "jqr_ros_msgs/srv/StatusLightScene",
            {"scene": 2, "ambient": 0, "restart_pattern": True},
            timeout=5.0,
        )

    def test_idle_maps_to_waiting_scene_1(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"accepted": True, "message": "OK"},
        }

        result = self.interface.set_robot_light_state(2, verify=False)

        self.assertTrue(result["success"])
        request = self.interface._call_ros2_service_async.call_args.args[3]
        self.assertEqual(request["scene"], 1)

    def test_all_named_scenes_are_supported(self):
        expected = {
            "off": 0, "waiting": 1, "working": 2, "safety_alert": 3,
            "fault": 4, "estop": 5, "low_battery": 6,
            "critical_battery": 7, "charging": 8, "upgrading": 9,
            "pairing": 10,
        }
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"accepted": True, "message": "OK"},
        }

        for name, value in expected.items():
            with self.subTest(scene=name):
                self.interface._call_ros2_service_async.reset_mock()
                result = self.interface.set_robot_light_state(scene=name, verify=False)
                self.assertTrue(result["success"])
                request = self.interface._call_ros2_service_async.call_args.args[3]
                self.assertEqual(request["scene"], value)

    def test_night_and_restart_false_are_forwarded(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"accepted": True, "message": "OK"},
        }

        result = self.interface.set_robot_light_state(
            scene="charging", ambient="night", restart_pattern=False,
            verify=False
        )

        self.assertTrue(result["success"])
        request = self.interface._call_ros2_service_async.call_args.args[3]
        self.assertEqual(
            request,
            {"scene": 8, "ambient": 1, "restart_pattern": False},
        )

    def test_numeric_scene_is_supported(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"accepted": True, "message": "OK"},
        }

        result = self.interface.set_robot_light_state(
            scene=10, ambient=1, verify=False
        )

        self.assertTrue(result["success"])
        request = self.interface._call_ros2_service_async.call_args.args[3]
        self.assertEqual(request["scene"], 10)
        self.assertEqual(request["ambient"], 1)

    def test_mcu_rejection_is_propagated(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"accepted": False, "message": "MCU busy"},
        }

        result = self.interface.set_robot_light_state("1")

        self.assertFalse(result["success"])
        self.assertEqual(result["error_msg"], "MCU busy")

    def test_service_failure_is_propagated(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": False,
            "error_msg": "服务 /set_status_light_scene 未在 5.0 秒内变为可用",
        }

        result = self.interface.set_robot_light_state("2")

        self.assertFalse(result["success"])
        self.assertIn("未在", result["error_msg"])

    def test_invalid_state_does_not_call_ros(self):
        result = self.interface.set_robot_light_state("3")

        self.assertFalse(result["success"])
        self.interface._call_ros2_service_async.assert_not_called()

    def test_invalid_extended_params_do_not_call_ros(self):
        cases = [
            {"scene": "unknown"},
            {"scene": 11},
            {"scene": "working", "ambient": "evening"},
            {"scene": "working", "restart_pattern": "true"},
            {"state": "1", "scene": "working"},
        ]
        for params in cases:
            with self.subTest(params=params):
                self.interface._call_ros2_service_async.reset_mock()
                result = self.interface.set_robot_light_state(**params)
                self.assertFalse(result["success"])
                self.interface._call_ros2_service_async.assert_not_called()


class RobotLightDispatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_dispatches_upper_protocol_to_ros_interface(self):
        agent = SmartRobotAgent.__new__(SmartRobotAgent)
        agent.ros2_interface = MagicMock()
        agent.ros2_interface.set_robot_light_state.return_value = {
            "type": "set_robot_light_state",
            "success": True,
            "error_msg": "",
        }

        result = await agent._execute_task_by_type(
            "set_robot_light_state", {"state": "1"}
        )

        agent.ros2_interface.set_robot_light_state.assert_called_once_with(state="1")
        self.assertEqual(
            result,
            {"type": "set_robot_light_state", "success": True, "error_msg": ""},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
