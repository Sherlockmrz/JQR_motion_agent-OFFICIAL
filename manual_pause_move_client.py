#!/usr/bin/env python3
"""手动向 Motion Agent 发送一次 pause_move，便于 VS Code 联调。"""

import argparse
import asyncio
import json

import websockets


async def send_pause_move(uri: str) -> None:
    request = {"type": "pause_move", "params": {}}
    print("发送:", json.dumps(request, ensure_ascii=False))

    async with websockets.connect(uri, open_timeout=5.0) as websocket:
        await websocket.send(json.dumps(request, ensure_ascii=False))
        response = await asyncio.wait_for(websocket.recv(), timeout=15.0)

    print("收到:", response)


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 Motion Agent pause_move")
    parser.add_argument(
        "--uri",
        default="ws://127.0.0.1:8766",
        help="Motion Agent WebSocket 地址",
    )
    args = parser.parse_args()
    asyncio.run(send_pause_move(args.uri))


if __name__ == "__main__":
    main()
