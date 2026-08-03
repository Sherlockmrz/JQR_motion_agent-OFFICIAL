#!/usr/bin/env python3
"""Offline tests for the documented MCU auxiliary ROS 2 service pipeline."""

import unittest
from unittest.mock import MagicMock

from smart_robot_agent import ROS2Interface


class McuAuxServiceTest(unittest.TestCase):
    def setUp(self):
        self.interface = ROS2Interface.__new__(ROS2Interface)
        self.interface._call_ros2_service_async = MagicMock()

    @staticmethod
    def medicine_status(state, seq=7, target=1, source=2, faults=0):
        return {
            "success": True,
            "response": {
                "valid": True,
                "uptime_ms": 100,
                "state": state,
                "target_command": target,
                "command_source": source,
                "io_flags": 0x0D,
                "fault_flags": faults,
                "current_ma": 120,
                "angle_raw": 456,
                "last_command_seq": seq,
                "last_result": 0,
                "message": "OK",
            },
        }

    def test_clear_fault_uses_documented_service(self):
        self.interface._call_ros2_service_async.return_value = {
            "success": True,
            "response": {"result_number": 1, "result_msg": "cleared"},
        }
        result = self.interface.clear_fault("0xffffffff")
        self.assertTrue(result["success"])
        self.interface._call_ros2_service_async.assert_called_once_with(
            "/clear_fault", 1, "jqr_ros_msgs/srv/ClearFault",
            {"fault_mask": 0xFFFFFFFF}, timeout=5.0,
        )

    def test_light_is_verified_against_mcu_feedback(self):
        self.interface._call_ros2_service_async.side_effect = [
            {
                "success": True,
                "response": {"accepted": True, "message": "ACK"},
            },
            {
                "success": True,
                "response": {
                    "valid": True, "uptime_ms": 10, "last_command_seq": 3,
                    "control_mode": 2, "scene": 2, "ambient": 0,
                    "effect": 3, "flags": 3,
                    "r_permille": 0, "g_permille": 1000,
                    "b_permille": 0, "w_permille": 0, "message": "OK",
                },
            },
        ]
        result = self.interface.set_status_light_scene(
            "working", ambient="day", restart_pattern=True,
            verify=True, timeout=0.2,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"]["effect_name"], "breathe")

    def test_open_waits_for_matching_sequence_and_terminal_state(self):
        self.interface._call_ros2_service_async.side_effect = [
            {
                "success": True,
                "response": {"accepted": True, "command_seq": 7, "message": "ACK"},
            },
            self.medicine_status(state=3),
            self.medicine_status(state=4),
        ]
        result = self.interface.set_medicine_box_command(
            "open", wait=True, timeout=0.5, poll_interval=0.02
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["completed"])
        self.assertEqual(result["status"]["state_name"], "open")

    def test_wrong_sequence_cannot_complete_the_command(self):
        self.interface._call_ros2_service_async.side_effect = [
            {
                "success": True,
                "response": {"accepted": True, "command_seq": 7, "message": "ACK"},
            },
            self.medicine_status(state=4, seq=6),
            self.medicine_status(state=4, seq=7),
        ]
        result = self.interface.set_medicine_box_command(
            1, wait=True, timeout=0.5, poll_interval=0.02
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["status"]["last_command_seq"], 7)

    def test_matching_fault_is_reported_as_failure(self):
        self.interface._call_ros2_service_async.side_effect = [
            {
                "success": True,
                "response": {"accepted": True, "command_seq": 7, "message": "ACK"},
            },
            self.medicine_status(state=7, faults=4),
        ]
        result = self.interface.set_medicine_box_command(
            "open", wait=True, timeout=0.2, poll_interval=0.02
        )
        self.assertFalse(result["success"])
        self.assertIn("0x0004", result["error_msg"])

    def test_legacy_switch_maps_to_native_close(self):
        self.interface.set_medicine_box_command = MagicMock(return_value={
            "type": "set_medicine_box_command", "success": True,
        })
        result = self.interface.set_medicine_box_switch(False, speed_stage=2)
        self.assertTrue(result["success"])
        self.interface.set_medicine_box_command.assert_called_once_with(
            command=2, wait=True, timeout=12.0
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
