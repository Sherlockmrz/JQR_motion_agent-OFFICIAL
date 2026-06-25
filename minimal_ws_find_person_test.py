#!/usr/bin/env python3
"""Minimal WebSocket client for testing the motion agent."""

import argparse
import asyncio
import json

import websockets


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one find-person command to the motion agent WebSocket server."
    )
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    parser.add_argument("--person", default="张三")
    parser.add_argument("--prompt", default=None)
    parser.add_argument(
        "--task",
        default="find_person",
        choices=["find_person", "go_find_person"],
        help="find_person is a static lookup; go_find_person may trigger navigation.",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    prompt = args.prompt or f"请找一下{args.person}"
    payload = {
        "type": args.task,
        "params": {
            "obj_name": args.person,
            "user_prompt": prompt,
        },
    }

    print(f"Connecting to {args.uri}")
    print("Agent supports WebSocket communication; sending one find-person command:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    async with websockets.connect(args.uri, open_timeout=10) as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        response = await asyncio.wait_for(ws.recv(), timeout=args.timeout)

    print("Received response:")
    try:
        print(json.dumps(json.loads(response), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
