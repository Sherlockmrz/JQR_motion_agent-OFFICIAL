#!/usr/bin/env python3
"""Interactive one-terminal client for VLN search and stop_move testing."""

import argparse
import asyncio
import json
import threading
from datetime import datetime

import websockets


def start_terminal_reader(loop, command_queue):
    """Read commands from the controlling terminal even when run via heredoc."""

    def reader():
        try:
            with open("/dev/tty", "r", encoding="utf-8") as terminal:
                for line in terminal:
                    command = line.strip().lower()
                    if command:
                        asyncio.run_coroutine_threadsafe(
                            command_queue.put(command), loop
                        )
        except OSError:
            return

    threading.Thread(target=reader, daemon=True, name="SearchStopInput").start()


async def send_stop(websocket):
    payload = {
        "type": "stop_move",
        "params": {
            "user_prompt": "停止当前找人找物任务",
        },
    }
    print("Sending stop_move:", json.dumps(payload, ensure_ascii=False))
    await websocket.send(json.dumps(payload, ensure_ascii=False))


async def receive_search(websocket, task_type, state, finished):
    try:
        while True:
            message = await asyncio.wait_for(websocket.recv(), timeout=240.0)
            timestamp = datetime.now().strftime("%H:%M:%S")
            data = json.loads(message)

            if "command" in data:
                print(f"[{timestamp}] VLN推理: {data.get('command', '')}")
            else:
                print(f"[{timestamp}] Agent返回: {json.dumps(data, ensure_ascii=False)}")

            if data.get("type") == "stop_move" and "success" in data:
                state["stop_finished"] = True
                print("stop_move result:", json.dumps(data, ensure_ascii=False))
            elif data.get("type") == task_type and "success" in data and "command" not in data:
                state["search_finished"] = True

            if state["search_finished"] and (
                not state["stop_requested"] or state["stop_finished"]
            ):
                return
    except asyncio.TimeoutError:
        print("240秒内没有收到新消息，停止等待")
        return None
    finally:
        finished.set()


async def main():
    parser = argparse.ArgumentParser(
        description="在一个终端中测试找人/找物，并输入 stop 中断任务"
    )
    parser.add_argument("--uri", default="ws://127.0.0.1:8766")
    parser.add_argument("--task", choices=("go_to_object", "go_find_person"), default="go_to_object")
    parser.add_argument("--name", default="帽子", help="物体名称或人员名称")
    args = parser.parse_args()

    params = {"obj_name": args.name}
    if args.task == "go_find_person":
        params["user_prompt"] = f"去找{args.name}"
    payload = {"type": args.task, "params": params}

    command_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    start_terminal_reader(loop, command_queue)

    async with websockets.connect(args.uri, ping_interval=None) as search_websocket:
        print("Sending search:", json.dumps(payload, ensure_ascii=False))
        print("任务执行中输入 stop 并回车，可停止整个找人/找物流程。")
        await search_websocket.send(json.dumps(payload, ensure_ascii=False))

        finished = asyncio.Event()
        state = {
            "stop_requested": False,
            "stop_finished": False,
            "search_finished": False,
        }
        receive_task = asyncio.create_task(
            receive_search(search_websocket, args.task, state, finished)
        )

        while not finished.is_set():
            command_task = asyncio.create_task(command_queue.get())
            finished_task = asyncio.create_task(finished.wait())
            done, pending = await asyncio.wait(
                (command_task, finished_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

            if finished_task in done:
                break

            command = command_task.result()
            if command in ("stop", "s"):
                if state["stop_requested"]:
                    print("stop_move 已发送，正在等待结果")
                    continue
                state["stop_requested"] = True
                try:
                    await send_stop(search_websocket)
                except Exception as exc:
                    print(f"stop_move 发送失败: {exc}")
            else:
                print("可用命令: stop")

        await receive_task


if __name__ == "__main__":
    asyncio.run(main())
