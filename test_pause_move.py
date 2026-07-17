#!/usr/bin/env python3
"""pause_move 可行性测试：使用 Mock VLN，不依赖 ROS2 或真机。"""

import json
import unittest

import websockets

from smart_robot_agent import SmartRobotAgent


class MockVLN:
    def __init__(self, response):
        self.response = response
        self.received = []

    async def handler(self, websocket):
        request = json.loads(await websocket.recv())
        self.received.append(request)
        await websocket.send(json.dumps(self.response, ensure_ascii=False))


class FakeUpstreamWebSocket:
    """直接捕获 WebSocketControlServer 发给交互系统的最终响应。"""

    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(json.loads(message))


class PauseMoveTest(unittest.IsolatedAsyncioTestCase):
    async def call_pause_move(self, vln_response):
        mock_vln = MockVLN(vln_response)

        async with websockets.serve(mock_vln.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            agent = SmartRobotAgent()
            agent.local_model_uri = f"ws://127.0.0.1:{port}/ws/navigate"
            agent._running = True

            result = await agent.execute_task(
                {"type": "pause_move", "params": {}}
            )

        return result, mock_vln.received

    async def test_pause_move_success_pipeline(self):
        result, received = await self.call_pause_move(
            {"result": True, "error_msg": ""}
        )

        self.assertEqual(received, [{"type": "pause"}])
        self.assertEqual(
            result,
            {"type": "pause_move", "success": True, "error_msg": ""},
        )

    async def test_pause_move_propagates_vln_failure(self):
        result, received = await self.call_pause_move(
            {"result": False, "error_msg": "当前没有可暂停任务"}
        )

        self.assertEqual(received, [{"type": "pause"}])
        self.assertFalse(result["success"])
        self.assertEqual(result["error_msg"], "当前没有可暂停任务")

    async def test_pause_move_full_upstream_protocol(self):
        mock_vln = MockVLN({"result": True, "error_msg": ""})

        async with websockets.serve(mock_vln.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            agent = SmartRobotAgent()
            agent.local_model_uri = f"ws://127.0.0.1:{port}/ws/navigate"
            agent._running = True
            upstream = FakeUpstreamWebSocket()

            await agent.websocket_server._handle_message(
                upstream,
                json.dumps({"type": "pause_move", "params": {}}),
            )

        self.assertEqual(mock_vln.received, [{"type": "pause"}])
        self.assertEqual(
            upstream.sent,
            [{"type": "pause_move", "success": True, "error_msg": ""}],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
