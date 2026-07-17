#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests and optional smoke-test helpers for ``pause_move``.

Default usage (no ROS 2 or external VLN service required)::

    python -m unittest -v test_pause_move.py

Optional manual helpers::

    python test_pause_move.py --mock-vln --mode success
    python test_pause_move.py --live --uri ws://127.0.0.1:8766

The test module injects a small in-memory ``config`` module before importing
``smart_robot_agent``.  This keeps the tests independent of the project's
``.env`` file.
"""

import argparse
import asyncio
import importlib
import json
import sys
import threading
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import websockets


def _import_agent_without_project_env():
    """Import the agent with deterministic test configuration.

    ``config.py`` normally loads ``.env`` as an import side effect.  Replacing
    that module only for the duration of this import keeps this test isolated
    from local credentials and machine-specific settings.
    """

    if "smart_robot_agent" in sys.modules:
        return sys.modules["smart_robot_agent"]

    fake_config_module = types.ModuleType("config")
    fake_config_module.config = types.SimpleNamespace(
        AGENT_VERSION="test",
        ASM_JSON_PATH="asm_test.json",
        VIDEO_BASE_DIR="videos",
        DB_PATH="",
        USB_SERIAL_PORT="",
        USB_SERIAL_BAUDRATE=115200,
        USB_SERIAL_ENABLED=False,
        WEBSOCKET_HOST="127.0.0.1",
        WEBSOCKET_PORT=8766,
        LOCAL_MODEL_URI="ws://127.0.0.1:8000/ws/navigate",
        LLM_BACKEND="local_ws",
        OPENAI_API_KEY="",
        OPENAI_BASE_URL="http://127.0.0.1",
        OPENAI_MODEL="test",
        AGENT_MEMORY_SIZE=10,
        MAX_REACT_ITERATIONS=2,
        WELCOME_POSITION_FILE="welcome_position_test.txt",
    )

    previous_config_module = sys.modules.get("config")
    sys.modules["config"] = fake_config_module
    try:
        return importlib.import_module("smart_robot_agent")
    finally:
        if previous_config_module is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = previous_config_module


agent_module = _import_agent_without_project_env()
SmartRobotAgent = agent_module.SmartRobotAgent
WebSocketControlServer = agent_module.WebSocketControlServer


class _FakeUSBManager:
    """Small substitute used by execute_task/send_to_local_model."""

    def __init__(self):
        self.serial_manager = None
        self.messages = []

    async def send_message(self, message):
        self.messages.append(message)
        return True


class _FakeUpperWebSocket:
    """Captures replies produced by WebSocketControlServer._handle_message."""

    def __init__(self):
        self.remote_address = ("unit-test", 12345)
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)


def _make_bare_agent(active_tasks=None):
    """Create an Agent without invoking ROS/USB/WebSocket constructors."""

    agent = object.__new__(SmartRobotAgent)
    agent.active_navigation_tasks = set(active_tasks or [])
    agent.task_execution_lock = asyncio.Lock()
    agent._thread_local = threading.local()
    agent._connection_lock = threading.Lock()
    agent.local_model_uri = "ws://127.0.0.1:8000/ws/navigate"
    agent._running = True
    agent.usb_manager = _FakeUSBManager()
    return agent


class PauseMoveTests(unittest.IsolatedAsyncioTestCase):
    def test_pause_move_is_registered(self):
        fake_usb_manager = MagicMock()
        fake_usb_manager.serial_manager = None

        with patch.object(agent_module, "ROS2Interface", return_value=MagicMock()):
            with patch.object(
                agent_module,
                "USBCoordinateManager",
                return_value=fake_usb_manager,
            ):
                with patch.object(
                    agent_module,
                    "WebSocketControlServer",
                    return_value=MagicMock(),
                ):
                    agent = SmartRobotAgent()

        self.assertIn("pause_move", agent.known_task_types)

    async def test_success_sends_exact_vln_payload_and_preserves_task(self):
        agent = _make_bare_agent({"navigation-1"})
        agent.send_to_local_model = AsyncMock(
            return_value={"result": True, "error_msg": ""}
        )

        result = await agent.pause_move()

        agent.send_to_local_model.assert_awaited_once_with({"type": "pause"})
        self.assertIs(result["success"], True)
        self.assertEqual(result["type"], "pause_move")
        self.assertEqual(result.get("error_msg", ""), "")
        self.assertEqual(agent.active_navigation_tasks, {"navigation-1"})

    async def test_vln_result_failure_is_propagated(self):
        agent = _make_bare_agent()
        agent.send_to_local_model = AsyncMock(
            return_value={"result": False, "error_msg": "VLN拒绝暂停"}
        )

        result = await agent.pause_move()

        self.assertIs(result["success"], False)
        self.assertEqual(result["type"], "pause_move")
        self.assertEqual(result["error_msg"], "VLN拒绝暂停")

    async def test_legacy_success_field_is_supported(self):
        cases = (
            ({"success": True}, True, ""),
            ({"success": False, "error_msg": "legacy failure"}, False, "legacy failure"),
        )

        for response, expected_success, expected_error in cases:
            with self.subTest(response=response):
                agent = _make_bare_agent()
                agent.send_to_local_model = AsyncMock(return_value=response)

                result = await agent.pause_move()

                self.assertIs(result["success"], expected_success)
                self.assertEqual(result.get("error_msg", ""), expected_error)

    async def test_missing_or_non_boolean_status_is_failure(self):
        invalid_responses = (
            None,
            {},
            {"message": "没有最终状态"},
            {"result": "true"},
            {"result": 1},
            {"success": "false"},
            {"success": 0},
        )

        for response in invalid_responses:
            with self.subTest(response=response):
                agent = _make_bare_agent()
                agent.send_to_local_model = AsyncMock(return_value=response)

                result = await agent.pause_move()

                self.assertIs(result["success"], False)
                self.assertEqual(result["type"], "pause_move")
                self.assertTrue(result.get("error_msg"))

    async def test_timeout_and_transport_exception_are_failures(self):
        exceptions = (asyncio.TimeoutError(), RuntimeError("VLN connection lost"))

        for exception in exceptions:
            with self.subTest(exception=type(exception).__name__):
                agent = _make_bare_agent()
                agent.send_to_local_model = AsyncMock(side_effect=exception)

                result = await agent.pause_move()

                self.assertIs(result["success"], False)
                self.assertEqual(result["type"], "pause_move")
                self.assertTrue(result.get("error_msg"))

    async def test_dispatch_without_ros_and_with_no_active_task(self):
        agent = _make_bare_agent()
        self.assertFalse(hasattr(agent, "ros2_interface"))
        agent.pause_move = AsyncMock(return_value={"success": True})

        result = await SmartRobotAgent._execute_task_by_type(
            agent, "pause_move", {}
        )

        agent.pause_move.assert_awaited_once_with()
        self.assertIs(result["success"], True)
        self.assertEqual(result["type"], "pause_move")
        self.assertEqual(agent.active_navigation_tasks, set())

    async def test_upper_websocket_to_in_process_vln_round_trip(self):
        received_by_vln = []

        async def mock_vln_handler(websocket, path=None):
            del path
            request = json.loads(await websocket.recv())
            received_by_vln.append(request)
            await websocket.send(
                json.dumps({"result": True, "error_msg": ""}, ensure_ascii=False)
            )

        mock_vln_server = await websockets.serve(
            mock_vln_handler, "127.0.0.1", 0
        )
        port = mock_vln_server.sockets[0].getsockname()[1]

        agent = _make_bare_agent({"navigation-round-trip"})
        agent.local_model_uri = "ws://127.0.0.1:{}/ws/navigate".format(port)
        upper_websocket = _FakeUpperWebSocket()
        upper_server = WebSocketControlServer(agent, host="127.0.0.1", port=0)

        try:
            await asyncio.wait_for(
                upper_server._handle_message(
                    upper_websocket,
                    json.dumps(
                        {"type": "pause_move", "params": {}},
                        ensure_ascii=False,
                    ),
                ),
                timeout=5.0,
            )

            self.assertEqual(received_by_vln, [{"type": "pause"}])
            self.assertEqual(len(upper_websocket.sent_messages), 1)
            response = json.loads(upper_websocket.sent_messages[0])
            self.assertEqual(
                response,
                {
                    "success": True,
                    "error_msg": "",
                    "type": "pause_move",
                },
            )
            self.assertEqual(
                agent.active_navigation_tasks, {"navigation-round-trip"}
            )
        finally:
            agent._running = False
            downstream_websocket = getattr(
                agent._thread_local, "websocket", None
            )
            if downstream_websocket is not None:
                await downstream_websocket.close()
            mock_vln_server.close()
            await mock_vln_server.wait_closed()


async def _run_mock_vln(host, port, mode):
    async def handler(websocket, path=None):
        del path
        raw_request = await websocket.recv()
        print("VLN received: {}".format(raw_request), flush=True)

        if mode == "timeout":
            await asyncio.Future()
        elif mode == "failure":
            await websocket.send(
                json.dumps(
                    {"result": False, "error_msg": "mock VLN rejected pause"}
                )
            )
        else:
            await websocket.send(json.dumps({"result": True, "error_msg": ""}))

    async with websockets.serve(handler, host, port):
        print(
            "Mock VLN listening on ws://{}:{}/ws/navigate (mode={})".format(
                host, port, mode
            ),
            flush=True,
        )
        await asyncio.Future()


async def _run_live_client(uri, timeout):
    request = {"type": "pause_move", "params": {}}
    async with websockets.connect(uri, ping_interval=None) as websocket:
        await websocket.send(json.dumps(request, ensure_ascii=False))
        raw_response = await asyncio.wait_for(websocket.recv(), timeout=timeout)

    response = json.loads(raw_response)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return response.get("type") == "pause_move" and response.get("success") is True


def _main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mock-vln", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--mode", choices=("success", "failure", "timeout"), default="success")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    parser.add_argument("--timeout", type=float, default=10.0)
    args, unittest_args = parser.parse_known_args()

    if args.mock_vln:
        asyncio.run(_run_mock_vln(args.host, args.port, args.mode))
        return 0
    if args.live:
        ok = asyncio.run(_run_live_client(args.uri, args.timeout))
        return 0 if ok else 2

    unittest.main(argv=[sys.argv[0]] + unittest_args)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
