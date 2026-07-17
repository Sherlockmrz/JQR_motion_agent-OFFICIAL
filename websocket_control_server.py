# -*- coding: utf-8 -*-
"""WebSocket控制服务器 - 支持局域网终端控制"""
import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional
import websockets

logger = logging.getLogger(__name__)

# ============ 统一日志格式支撑：[trace=..][时间][标签] 内容 ============
# 当前任务上下文（机器人单任务串行，用全局即可）。WS 入口在连接/收命令时更新它，
# filter 会把 trace/label 注入到每一条日志记录里，从而所有模块的日志都带同样前缀。
class _LogContext:
    trace = "-"
    label = "系统"


log_context = _LogContext()


class _TraceFilter(logging.Filter):
    def filter(self, record):
        record.trace = getattr(log_context, "trace", "-")
        record.label = getattr(log_context, "label", "系统")
        return True


def install_trace_logging():
    """把 root 上的 handler 换成 [trace=..][时间][标签] 格式并注入 trace/label。
    在 smart_robot_agent 的 basicConfig 之后调用一次，对所有模块日志生效（1:1 保留每行）。"""
    fmt = logging.Formatter(
        "[trace=%(trace)s][%(asctime)s.%(msecs)03d][%(label)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers:
        h.setFormatter(fmt)
        h.addFilter(_TraceFilter())
    # websockets 库的 INFO（connection open / server listening）不需要，降到 WARNING
    logging.getLogger("websockets").setLevel(logging.WARNING)


# type -> 中文任务标签
TYPE_LABEL = {
    "find_person": "找人",
    "go_find_person": "找人",
    "find_object": "找物",
    "go_to_object": "找物",
    "follow_person": "跟随",
}


def _make_trace() -> str:
    """任务追踪号：连接建立时刻，格式 YYYYMMDD-HHMMSS。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


class WebSocketControlServer:
    """WebSocket控制服务器
    
    允许局域网内的其他终端通过WebSocket发送控制命令
    通信协议:
    入参: {"type": "go_to_door", "params": {}}
    返回: {"success": true/false, "error_msg": "..."}
    """
    
    def __init__(self, agent, host: str = "127.0.0.1", port: int = 8766):
        """初始化WebSocket控制服务器
        
        Args:
            agent: SmartRobotAgent实例
            host (str): 监听地址，默认0.0.0.0监听所有网卡
            port (int): 监听端口，默认8766
        """
        self.agent = agent
        self.host = host
        self.port = port
        
        # 连接管理
        self.connected_clients: set = set()
        self.clients_lock = threading.Lock()
        
        # 服务器状态
        self.server = None
        self.server_thread = None
        self.running = False
        
        # 统计信息
        self.total_messages = 0
        self.total_errors = 0
        
    def start(self) -> bool:
        """启动WebSocket服务器（在独立线程中运行）
        
        Returns:
            bool: 启动是否成功
        """
        try:
            if self.running:
                logger.warning(f"WebSocket控制服务器已在运行")
                return True
            
            logger.info(f"正在启动WebSocket控制服务器 ws://{self.host}:{self.port}")
            
            # 创建新的事件循环和线程
            self.running = True
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="WebSocketControlServer"
            )
            self.server_thread.start()
            
            # 等待服务器启动
            time.sleep(0.5)
            
            logger.info(f"WebSocket控制服务器已启动，监听端口: {self.port}")
            return True
            
        except Exception as e:
            logger.error(f"启动WebSocket控制服务器失败: {e}")
            self.running = False
            return False
    
    def _run_server(self):
        """在独立线程中运行WebSocket服务器"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.server_loop = loop  # 保存事件循环引用
            
            # 使用 async with 启动服务器（兼容 websockets 11.0+）
            async def run_server():
                async with websockets.serve(
                    self._handle_client,
                    self.host,
                    self.port,
                    ping_interval=None,  # 禁用 ping
                    ping_timeout=None    # 禁用 ping timeout
                ):
                    self.server = True  # 标记服务器已启动
                    logger.info(f"WebSocket服务器正在监听 {self.host}:{self.port}")
                    # 保持运行
                    await asyncio.Future()  # 永久等待
            
            loop.run_until_complete(run_server())
            
        except Exception as e:
            logger.error(f"WebSocket服务器运行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
    
    async def _handle_client(self, websocket):
        """处理客户端连接（兼容 websockets 11.0+）
        
        Args:
            websocket: WebSocket连接对象
        """
        client_addr = websocket.remote_address
        _ip = f"{client_addr[0]}:{client_addr[1]}" if client_addr else "未知"
        # 新会话：设置 trace 上下文（命令到达前标签为“连接”）
        log_context.trace = _make_trace()
        log_context.label = "连接"
        logger.info("WebSocket 连接已打开，等待上层任务")
        logger.info(f"新客户端接入：{_ip}，Agent 已就绪可接收任务")
        
        # 添加到连接列表
        with self.clients_lock:
            self.connected_clients.add(websocket)
        
        try:
            # 持续接收消息
            async for message in websocket:
                try:
                    await self._handle_message(websocket, message)
                except Exception as e:
                    logger.error(f"处理消息异常: {e}")
                    self.total_errors += 1
                    # 发送错误响应
                    error_response = {
                        "success": False,
                        "error_msg": f"处理消息失败: {str(e)}"
                    }
                    await websocket.send(json.dumps(error_response, ensure_ascii=False))
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"客户端 {_ip} 已断开连接，本次会话结束")
        except Exception as e:
            logger.error(f"WebSocket连接异常: {e}")
        finally:
            # 从连接列表移除
            with self.clients_lock:
                self.connected_clients.discard(websocket)
    
    async def _handle_message(self, websocket, message: str):
        """处理接收到的消息
        
        Args:
            websocket: WebSocket连接对象
            message: 消息内容
        """
        self.total_messages += 1
        start_time = time.time()
        
        try:
            # 解析消息
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.error(f"JSON解析失败: {message}")
                response = {
                    "success": False,
                    "error_msg": "无效的JSON格式"
                }
                await websocket.send(json.dumps(response, ensure_ascii=False))
                return
            
            # 验证消息格式
            if not isinstance(data, dict):
                response = {
                    "success": False,
                    "error_msg": "消息必须是JSON对象格式"
                }
                await websocket.send(json.dumps(response, ensure_ascii=False))
                return
            
            # 检查是否有type字段
            if "type" not in data:
                response = {
                    "success": False,
                    "error_msg": "消息必须包含type字段"
                }
                await websocket.send(json.dumps(response, ensure_ascii=False))
                return
            
            task_type = data.get("type")
            task_params = data.get("params", {})

            # ===== 更新日志上下文：标签切换成任务类型（trace 沿用连接时的） =====
            log_context.label = TYPE_LABEL.get(task_type, task_type or "任务")
            obj_name = task_params.get("obj_name", "")
            user_prompt = task_params.get("user_prompt", "")

            logger.info(f'上层发来任务：找{obj_name}，原始指令="{user_prompt}"')
            
            # 调用agent执行任务
            task = {
                "type": task_type,
                "params": task_params
            }
            
            # 检查agent是否可用
            if not self.agent:
                response = {
                    "success": False,
                    "error_msg": "Agent不可用"
                }
                await websocket.send(json.dumps(response, ensure_ascii=False))
                return

            # 执行任务（使用agent的execute_task方法）
            try:
                # ===== 开始执行：按类型给出一句易读说明 =====
                if task_type in ("go_find_person", "go_to_object", "follow_person"):
                    _vln_cmd, _vln_id = {
                        "go_find_person": ("go_to_person", "person_id"),
                        "go_to_object": ("go_to_object", "object_id"),
                        "follow_person": ("follow_person", "person_id"),
                    }[task_type]
                    logger.info(f"Motion Agent 开始执行，转换成 VLN 导航请求：{_vln_cmd}/{_vln_id}={obj_name}")
                elif task_type == "find_person":
                    logger.info("Motion Agent 开始执行，本地相机静态找人")
                elif task_type == "find_object":
                    logger.info("Motion Agent 开始执行找物任务")
                else:
                    logger.info(f"Motion Agent 开始执行：{task_type}")

                result = await self.agent.execute_task(task)

                # ===== 执行结束：如实回报 success 与返回字段 =====
                _kind = {
                    "go_find_person": "VLN 导航", "go_to_object": "VLN 导航",
                    "follow_person": "VLN 导航", "find_person": "找人", "find_object": "找物",
                }.get(task_type, "任务")
                _succ = str(result.get("success")).lower()
                _keys = "/".join(str(k) for k in result.keys())
                logger.info(f"{_kind}执行结束，返回 success={_succ}（返回字段 {_keys}）")

                # 构造响应（按照协议格式）
                response = {
                    "success": result.get("success", False),
                    "error_msg": result.get("error_msg", "") if not result.get("success") else ""
                }

                # 如果有额外的数据字段，也添加到响应中
                for key in ["result", "description", "data"]:
                    if key in result:
                        response[key] = result[key]

                # 保持type字段用于识别
                response["type"] = task_type

            except Exception as e:
                logger.error(f"任务执行异常：{e}")
                import traceback
                traceback.print_exc()
                response = {
                    "success": False,
                    "error_msg": f"任务执行失败: {str(e)}",
                    "type": task_type
                }

            # 发送响应
            elapsed = time.time() - start_time
            _succ = str(response.get("success")).lower()
            _res_word = "成功" if response.get("success") else "失败"
            logger.info(f"准备回复上层：任务{_res_word} success={_succ}，本次耗时 {elapsed:.2f} 秒")
            try:
                await websocket.send(json.dumps(response, ensure_ascii=False))
            except websockets.exceptions.ConnectionClosed:
                with self.clients_lock:
                    self.connected_clients.discard(websocket)
                logger.info("客户端已断开，最终结果无法发送；任务本身已执行完成")
                return
            _addr = websocket.remote_address
            _rip = f"{_addr[0]}:{_addr[1]}" if _addr else ""
            logger.info(f"结果已回复给客户端 {_rip}".rstrip())

        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            self.total_errors += 1
            response = {
                "success": False,
                "error_msg": f"处理失败: {str(e)}"
            }
            try:
                await websocket.send(json.dumps(response, ensure_ascii=False))
            except Exception:
                pass
    
    async def stop_async(self):
        """异步停止WebSocket服务器（正确等待连接关闭）"""
        try:
            logger.info(f"正在停止WebSocket控制服务器...")

            self.running = False

            # 关闭所有客户端连接并等待完成
            close_tasks = []
            with self.clients_lock:
                for client in list(self.connected_clients):
                    try:
                        close_tasks.append(client.close())
                    except Exception:
                        pass
                self.connected_clients.clear()

            # 等待所有连接关闭
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            # 停止服务器线程的事件循环
            if hasattr(self, 'server_loop') and self.server_loop:
                self.server_loop.call_soon_threadsafe(self.server_loop.stop)

            self.server = None

            logger.info(f"WebSocket控制服务器已停止，统计: 消息总数={self.total_messages}, 错误总数={self.total_errors}")

        except Exception as e:
            logger.error(f"停止WebSocket控制服务器失败: {e}")

    def stop(self):
        """停止WebSocket服务器（同步包装器）"""
        try:
            # 如果有事件循环，使用异步版本
            if hasattr(self, 'server_loop') and self.server_loop:
                asyncio.run_coroutine_threadsafe(self.stop_async(), self.server_loop).result(timeout=5.0)
            else:
                # 否则直接设置标志
                self.running = False
                with self.clients_lock:
                    self.connected_clients.clear()
        except Exception as e:
            logger.error(f"停止WebSocket控制服务器失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取服务器统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self.clients_lock:
            client_count = len(self.connected_clients)
        
        return {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "connected_clients": client_count,
            "total_messages": self.total_messages,
            "total_errors": self.total_errors
        }
    
    async def broadcast_message(self, message: Dict[str, Any]) -> int:
        """向所有连接的客户端广播消息
        
        Args:
            message: 要广播的消息
            
        Returns:
            int: 成功发送的客户端数量
        """
        if not self.running:
            return 0
        
        message_str = json.dumps(message, ensure_ascii=False)
        success_count = 0
        
        with self.clients_lock:
            clients = list(self.connected_clients)
        
        closed_clients = []
        for client in clients:
            try:
                await client.send(message_str)
                success_count += 1
            except websockets.exceptions.ConnectionClosed:
                closed_clients.append(client)
            except Exception as e:
                logger.error(f"广播消息失败: {e}")

        if closed_clients:
            with self.clients_lock:
                for client in closed_clients:
                    self.connected_clients.discard(client)
            logger.info(f"跳过 {len(closed_clients)} 个已断开的 WebSocket 客户端")

        return success_count
