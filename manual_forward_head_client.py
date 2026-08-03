#!/usr/bin/env python3
"""通过上层 WebSocket 协议手动测试 forward_head。"""

import argparse
import asyncio
import json

import websockets


async def main(uri: str, angle: float, turn_speed: int) -> None:
    request = {
        "type": "forward_head",
        "params": {
            "angle": angle,
            "turn_speed": turn_speed,
        },
    }
    print("发送:", json.dumps(request, ensure_ascii=False))
    async with websockets.connect(uri, open_timeout=5) as websocket:
        await websocket.send(json.dumps(request, ensure_ascii=False))
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=40))
    print("收到:", json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("angle", type=float, help="前倾角度，单位为弧度；255使用默认15度")
    parser.add_argument("--turn-speed", type=int, choices=[0, 1, 2], default=2)
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    args = parser.parse_args()
    asyncio.run(main(args.uri, args.angle, args.turn_speed))
