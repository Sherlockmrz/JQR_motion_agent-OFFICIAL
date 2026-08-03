#!/usr/bin/env python3
"""Simulate upper-system WebSocket requests for Agent MCU auxiliary tasks."""

import argparse
import asyncio
import json
import sys
from typing import Any, Dict

import websockets


async def call_agent(uri: str, request: Dict[str, Any], timeout: float) -> int:
    print("SEND:")
    print(json.dumps(request, ensure_ascii=False, indent=2))

    async with websockets.connect(uri, open_timeout=5) as websocket:
        await websocket.send(json.dumps(request, ensure_ascii=False))
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
            response = json.loads(raw)
            if (
                isinstance(response, dict)
                and response.get("type") == request["type"]
                and "success" in response
            ):
                break
            print("IGNORE unrelated message:")
            print(json.dumps(response, ensure_ascii=False, indent=2))

    print("RECV:")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("success") is True else 2


def parse_uint32(value: str) -> int:
    number = int(value, 0)
    if not 0 <= number <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("mask must be in uint32 range")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    subparsers = parser.add_subparsers(dest="action", required=True)

    light = subparsers.add_parser("light")
    light.add_argument(
        "scene",
        choices=(
            "off", "waiting", "working", "safety_alert", "fault", "estop",
            "low_battery", "critical_battery", "charging", "upgrading", "pairing",
        ),
    )
    light.add_argument("--ambient", choices=("day", "night"), default="day")
    light.add_argument("--no-restart", action="store_true")
    light.add_argument("--no-verify", action="store_true")
    light.add_argument("--timeout", type=float, default=3.0)

    subparsers.add_parser("light-status")

    medicine = subparsers.add_parser("medicine")
    medicine.add_argument("command", choices=("stop", "open", "close"))
    medicine.add_argument("--no-wait", action="store_true")
    medicine.add_argument("--timeout", type=float, default=12.0)
    medicine.add_argument("--poll-interval", type=float, default=0.1)

    subparsers.add_parser("medicine-status")

    clear_fault = subparsers.add_parser("clear-fault")
    clear_fault.add_argument("--mask", type=parse_uint32, default=0xFFFFFFFF)
    return parser


def make_request(args: argparse.Namespace) -> tuple[Dict[str, Any], float]:
    if args.action == "light":
        return {
            "type": "set_status_light_scene",
            "params": {
                "scene": args.scene,
                "ambient": args.ambient,
                "restart_pattern": not args.no_restart,
                "verify": not args.no_verify,
                "timeout": args.timeout,
            },
        }, args.timeout + 7.0
    if args.action == "light-status":
        return {"type": "get_status_light_state", "params": {}}, 10.0
    if args.action == "medicine":
        return {
            "type": "set_medicine_box_command",
            "params": {
                "command": args.command,
                "wait": not args.no_wait,
                "timeout": args.timeout,
                "poll_interval": args.poll_interval,
            },
        }, args.timeout + 7.0
    if args.action == "medicine-status":
        return {"type": "get_medicine_box_status", "params": {}}, 10.0
    return {
        "type": "clear_fault",
        "params": {"fault_mask": args.mask},
    }, 10.0


def main() -> int:
    args = build_parser().parse_args()
    request, receive_timeout = make_request(args)
    try:
        return asyncio.run(call_agent(args.uri, request, receive_timeout))
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
        print(f"WebSocket request failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
