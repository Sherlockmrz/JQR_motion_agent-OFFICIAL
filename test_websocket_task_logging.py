#!/usr/bin/env python3
"""新增Motion Agent任务的WebSocket日志元数据测试。"""

import json
import unittest

from websocket_control_server import (
    TASK_ACTION_TEXT,
    TYPE_LABEL,
    WebSocketControlServer,
    _make_trace,
    _params_for_log,
    log_context,
)


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

    def test_trace_ids_include_milliseconds_and_are_unique(self):
        traces = {_make_trace() for _ in range(10)}

        self.assertEqual(len(traces), 10)
        for trace in traces:
            self.assertRegex(trace, r"^\d{8}-\d{6}-\d{3}-\d{6}$")


class WebSocketPerTaskTraceTest(unittest.IsolatedAsyncioTestCase):
    async def test_each_message_gets_a_distinct_trace(self):
        captured_traces = []

        class FakeAgent:
            async def execute_task(self, task):
                captured_traces.append((task["type"], log_context.trace))
                return {"type": task["type"], "success": True}

        class FakeWebSocket:
            remote_address = ("127.0.0.1", 12345)

            def __init__(self):
                self.responses = []

            async def send(self, message):
                self.responses.append(json.loads(message))

        server = WebSocketControlServer(FakeAgent(), port=0)
        websocket = FakeWebSocket()
        await server._handle_message(
            websocket, json.dumps({"type": "go_to_object", "params": {}})
        )
        await server._handle_message(
            websocket, json.dumps({"type": "stop_move", "params": {}})
        )

        self.assertEqual([item[0] for item in captured_traces], ["go_to_object", "stop_move"])
        self.assertNotEqual(captured_traces[0][1], captured_traces[1][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
