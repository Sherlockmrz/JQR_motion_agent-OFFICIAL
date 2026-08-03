#!/usr/bin/env python3
"""Minimal WebSocket client for testing find-object commands."""

import argparse
import asyncio
import json

import websockets


async def receive_one(ws, timeout: float) -> None:
    response = await asyncio.wait_for(ws.recv(), timeout=timeout)
    print("Received response:")
    try:
        print(json.dumps(json.loads(response), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(response)


async def receive_until_idle(ws, timeout: float, idle_timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    count = 0

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            print(f"No final close condition; stopped after {timeout:.1f}s.")
            return

        wait_time = min(idle_timeout, remaining)
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=wait_time)
        except asyncio.TimeoutError:
            if count == 0:
                raise
            print(f"No more messages for {idle_timeout:.1f}s; stopping listen-all mode.")
            return

        count += 1
        print(f"Received message #{count}:")
        try:
            print(json.dumps(json.loads(response), ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print(response)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one find-object command to the motion agent WebSocket server."
    )
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    parser.add_argument("--object", "--obj", dest="object_name", default="水杯")
    parser.add_argument(
        "--prompt",
        default="",
        help="Original user instruction. Leave empty to avoid triggering LLM fallback.",
    )
    parser.add_argument(
        "--task",
        default="find_object",
        choices=["find_object", "go_to_object"],
        help="find_object checks known data; go_to_object may trigger navigation/VLN.",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--listen-all",
        action="store_true",
        help="Keep receiving messages until idle timeout instead of exiting after one response.",
    )
    parser.add_argument("--idle-timeout", type=float, default=5.0)
    args = parser.parse_args()

    params = {"obj_name": args.object_name}
    if args.task == "find_object":
        params["user_prompt"] = args.prompt
    elif args.prompt:
        print("Note: --prompt is ignored for go_to_object to match Motion Agent arguments.")

    payload = {
        "type": args.task,
        "params": params,
    }

    print(f"Connecting to {args.uri}")
    print("Agent supports WebSocket communication; sending one find-object command:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    async with websockets.connect(args.uri, open_timeout=10, ping_interval=None) as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        if args.listen_all:
            await receive_until_idle(ws, args.timeout, args.idle_timeout)
        else:
            await receive_one(ws, args.timeout)


if __name__ == "__main__":
    asyncio.run(main())
