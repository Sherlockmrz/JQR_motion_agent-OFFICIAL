#!/usr/bin/env python3
"""Offline tests for full search interruption via stop_move."""

import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import websockets

from config import AgentConfig
from test_pause_move_extended import _make_bare_agent, agent_module


class StopMoveInterruptTests(unittest.IsolatedAsyncioTestCase):
    def test_agent_log_labels_are_chinese_and_motor_progress_is_silent(self):
        source = Path("smart_robot_agent.py").read_text(encoding="utf-8")

        self.assertNotIn("组合电机任务 {task_id} 进度:", source)
        self.assertNotIn("组合电机任务 {task_id} 最终结果:", source)
        self.assertNotIn("组合电机任务 {task_id} 结果:", source)
        self.assertNotIn("[WAIT_MOTOR]", source)
        self.assertNotIn("[SEARCH_TASK]", source)
        self.assertNotIn("[SEARCH_POSE]", source)
        self.assertIn("[等待电机]", source)
        self.assertIn("[搜索任务]", source)
        self.assertIn("[搜索姿态]", source)

    def test_default_vln_port_is_8001(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOCAL_MODEL_URI", None)
            self.assertEqual(
                AgentConfig().LOCAL_MODEL_URI,
                "ws://127.0.0.1:8001/ws/navigate",
            )

    async def test_search_task_is_registered_until_completion(self):
        agent = _make_bare_agent()
        agent._task_interrupted = False
        started = asyncio.Event()
        release = asyncio.Event()

        async def execute_by_type(task_type, params):
            del params
            started.set()
            await release.wait()
            if agent._task_interrupted:
                return agent._interrupted_search_result(task_type)
            return {"type": task_type, "success": True}

        agent._execute_task_by_type = execute_by_type
        execution = asyncio.create_task(
            agent.execute_task(
                {"type": "go_to_object", "params": {"obj_name": "帽子"}}
            )
        )

        await asyncio.wait_for(started.wait(), timeout=1.0)
        self.assertTrue(agent.has_active_navigation_tasks())

        agent._task_interrupted = True
        release.set()
        result = await asyncio.wait_for(execution, timeout=1.0)

        self.assertIs(result["interrupted"], True)
        self.assertEqual(agent.active_navigation_tasks, set())

    async def test_stop_move_interrupts_flow_and_uses_control_connection(self):
        agent = _make_bare_agent({"go_to_object:123"})
        agent._task_interrupted = False
        agent._send_control_to_local_model = AsyncMock(
            return_value={"success": True}
        )

        with patch.object(agent_module, "ROS2_AVAILABLE", False):
            result = await agent.stop_move()

        agent._send_control_to_local_model.assert_awaited_once_with({
            "type": "stop",
            "user_prompt": "停止当前找人找物任务",
        })
        self.assertIs(agent._task_interrupted, True)
        self.assertEqual(agent.active_navigation_tasks, set())
        self.assertIs(result["success"], True)
        self.assertIs(result["vln_stopped"], True)
        self.assertIs(result["interrupted"], True)

    async def test_vln_timeout_stops_vln_and_chassis(self):
        agent = _make_bare_agent()
        agent._send_control_to_local_model = AsyncMock(
            return_value={"success": True}
        )
        agent._publish_chassis_zero_velocity = AsyncMock(
            return_value=(True, "")
        )

        result = await agent._stop_timed_out_vln_task()

        agent._send_control_to_local_model.assert_awaited_once_with({
            "type": "stop",
            "user_prompt": "Agent等待VLN最终结果超时，停止当前任务",
        })
        agent._publish_chassis_zero_velocity.assert_awaited_once_with()
        self.assertIs(result["vln_stopped"], True)
        self.assertIs(result["chassis_stopped"], True)

    async def test_control_helper_opens_connection_and_sends_stop(self):
        requests = []

        async def handler(websocket, path=None):
            del path
            requests.append(json.loads(await websocket.recv()))
            await websocket.send(json.dumps({"result": True}))

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        agent = _make_bare_agent()
        agent.local_model_uri = f"ws://127.0.0.1:{port}/ws/navigate"

        try:
            payload = {
                "type": "stop",
                "user_prompt": "停止当前找人找物任务",
            }
            result = await agent._send_control_to_local_model(payload)
            self.assertEqual(requests, [payload])
            self.assertIs(result["result"], True)
        finally:
            server.close()
            await server.wait_closed()

    async def test_one_websocket_can_send_search_then_standard_stop(self):
        stopped = asyncio.Event()

        class FakeAgent:
            async def execute_task(self, task):
                if task["type"] == "go_to_object":
                    await stopped.wait()
                    return {
                        "type": "go_to_object",
                        "success": False,
                        "interrupted": True,
                        "error_msg": "任务已被 stop_move 中断",
                    }
                if task["type"] == "stop_move":
                    self.stop_params = task["params"]
                    stopped.set()
                    return {
                        "type": "stop_move",
                        "success": True,
                        "interrupted": True,
                        "had_active_task": True,
                        "vln_stopped": True,
                        "chassis_stopped": True,
                    }
                return {"type": task["type"], "success": False}

        fake_agent = FakeAgent()
        upper_server = agent_module.WebSocketControlServer(
            fake_agent, host="127.0.0.1", port=0
        )
        upper_server.running = True
        server = await websockets.serve(upper_server._handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as websocket:
                await websocket.send(json.dumps({
                    "type": "go_to_object",
                    "params": {"obj_name": "帽子"},
                }, ensure_ascii=False))
                await websocket.send(json.dumps({
                    "type": "stop_move",
                    "params": {"user_prompt": "停止当前找人找物任务"},
                }, ensure_ascii=False))

                responses = [
                    json.loads(await asyncio.wait_for(websocket.recv(), timeout=2.0)),
                    json.loads(await asyncio.wait_for(websocket.recv(), timeout=2.0)),
                ]

            self.assertEqual(
                fake_agent.stop_params,
                {"user_prompt": "停止当前找人找物任务"},
            )
            self.assertEqual(
                {response["type"] for response in responses},
                {"go_to_object", "stop_move"},
            )
            search_response = next(
                response for response in responses
                if response["type"] == "go_to_object"
            )
            self.assertIs(search_response["interrupted"], True)
        finally:
            server.close()
            await server.wait_closed()

    async def test_vln_reasoning_is_logged_and_broadcast(self):
        async def handler(websocket, path=None):
            del path
            await websocket.recv()
            await websocket.send(json.dumps({"message": "向前探索并检查桌面"}, ensure_ascii=False))
            await websocket.send(json.dumps({"success": True}, ensure_ascii=False))

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        agent = _make_bare_agent()
        agent.local_model_uri = f"ws://127.0.0.1:{port}/ws/navigate"
        agent.usb_manager.serial_enabled = True
        agent.websocket_server = type(
            "FakeServer",
            (),
            {"broadcast_message": AsyncMock(return_value=1)},
        )()

        try:
            with self.assertLogs(agent_module.logger, level="INFO") as captured:
                result = await agent.send_to_local_model(
                    {"type": "go_to_object", "params": {"obj_name": "帽子"}}
                )

            self.assertIs(result["success"], True)
            self.assertTrue(
                any("VLN推理：向前探索并检查桌面" in line for line in captured.output)
            )
            agent.websocket_server.broadcast_message.assert_awaited_once_with(
                {"type": "go_to_object", "command": "向前探索并检查桌面"}
            )
        finally:
            websocket = getattr(agent._thread_local, "websocket", None)
            if websocket is not None:
                await websocket.close()
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
