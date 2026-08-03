#!/usr/bin/env python3
"""通过上层 WebSocket 协议手动测试 Motion Agent 机器状态灯。"""

import argparse
import asyncio
import json

import websockets


async def main(uri: str, state: str, scene: str, ambient: str,
               restart_pattern: bool) -> None:
    params = {
        "ambient": ambient,
        "restart_pattern": restart_pattern,
    }
    if scene is not None:
        params["scene"] = scene
    else:
        params["state"] = state

    request = {
        "type": "set_robot_light_state",
        "params": params,
    }
    print("发送:", json.dumps(request, ensure_ascii=False))
    async with websockets.connect(uri, open_timeout=5) as websocket:
        await websocket.send(json.dumps(request, ensure_ascii=False))
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
    print("收到:", json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "state", nargs="?", choices=["1", "2"],
        help="兼容旧协议：1=working，2=idle",
    )
    parser.add_argument(
        "--scene",
        choices=[
            "off", "waiting", "working", "safety_alert", "fault", "estop",
            "low_battery", "critical_battery", "charging", "upgrading", "pairing",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
        ],
        help="完整场景名称或0到10",
    )
    parser.add_argument("--ambient", choices=["day", "night"], default="day")
    parser.add_argument(
        "--no-restart", action="store_true",
        help="不重新开始呼吸或闪烁相位",
    )
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    args = parser.parse_args()
    if args.state is None and args.scene is None:
        parser.error("必须提供旧版state参数1/2，或使用--scene指定场景")
    if args.state is not None and args.scene is not None:
        parser.error("state和--scene不能同时使用")
    asyncio.run(main(
        args.uri,
        args.state,
        args.scene,
        args.ambient,
        not args.no_restart,
    ))
