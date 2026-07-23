#!/usr/bin/env python3
"""新增Motion Agent任务的WebSocket日志元数据测试。"""

import unittest

from websocket_control_server import TASK_ACTION_TEXT, TYPE_LABEL, _params_for_log


class WebSocketTaskLoggingTest(unittest.TestCase):
    def test_new_task_groups_have_readable_labels_and_actions(self):
        task_types = {
            "set_medicine_box_command",
            "get_medicine_box_status",
            "set_robot_light_state",
            "set_status_light_scene",
            "get_status_light_state",
            "wake_turn_to_person",
            "forward_head",
            "set_four_combine_motor_control",
            "set_four_combine_waypoint_control",
        }

        for task_type in task_types:
            with self.subTest(task_type=task_type):
                self.assertIn(task_type, TYPE_LABEL)
                self.assertIn(task_type, TASK_ACTION_TEXT)

    def test_log_params_preserve_chinese_and_have_stable_key_order(self):
        rendered = _params_for_log({"scene": "working", "note": "工作灯"})

        self.assertEqual(rendered, '{"note": "工作灯", "scene": "working"}')


if __name__ == "__main__":
    unittest.main(verbosity=2)
