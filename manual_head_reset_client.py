#!/usr/bin/env python3
"""通过上层 WebSocket 协议手动测试 head_reset_to_zero。"""

import argparse
import asyncio
import json

import websockets


async def main(uri: str, turn_speed: int) -> None:
    request = {
        "type": "head_reset_to_zero",
        "params": {
            "turn_speed": turn_speed,
        },
    }
    print("发送:", json.dumps(request, ensure_ascii=False))
    async with websockets.connect(uri, open_timeout=5) as websocket:
        await websocket.send(json.dumps(request, ensure_ascii=False))
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=40))
    print("收到:", json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="让头颈yaw/roll/pitch绝对回到零位")
    parser.add_argument("--turn-speed", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    args = parser.parse_args()
    asyncio.run(main(args.uri, args.turn_speed))
