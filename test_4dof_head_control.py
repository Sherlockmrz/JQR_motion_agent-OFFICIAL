#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4自由度头颈控制场景测试脚本

覆盖根目录 1.png/2.png/3.png 中与头颈相关的测试场景。
本次测试不涉及底盘：所有命令都只下发 yaw/roll/pitch，明确不发送底盘位移/旋转控制。

坐标系：ROS2标准坐标系（头颈部正前方向）
- yaw: 偏航角（左右转头），正值=左转，负值=右转
- pitch: 俯仰角（上下点头），正值=低头，负值=抬头
- roll: 翻滚角（左右歪头），正值=向左歪，负值=向右歪
"""
import argparse
import asyncio
import json
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import websockets


DEFAULT_WS_URI = "ws://localhost:8766"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {msg}")


# ========================
# 头部 4 电机物理限位 (用户权威给定)
# ========================
# head_pitch  头部俯仰: ±20°,  80 deg/s
# neck_pitch  脖子俯仰: ±27°,  80 deg/s
# neck_roll   脖子侧倾: ±35°,  80 deg/s
# neck_yaw    脖子旋转: ±165°, 120 deg/s
#
# 脚本 yaw/pitch/roll 语义 → 物理轴映射:
#   yaw  (左右转头/横向)  → neck_yaw   (±165°)
#   roll (左右歪头/侧倾)  → neck_roll  (±35°)
#   pitch(上下点头)       → head_pitch (±20°)  ← 最受限轴，按它卡 pitch
#
# 安全工作范围：严格小于边界，且至少留 5° 余量（用户要求“最少跟边界小5度”）:
YAW_LIMIT_DEG = 160.0   # 165 - 5
PITCH_LIMIT_DEG = 15.0  # 20 - 5  (head_pitch 最受限)
ROLL_LIMIT_DEG = 30.0   # 35 - 5

# 全局最高速度档位：用户要求所有动作一律跑最快档。
MAX_SPEED_LEVEL = 2


def deg(value: float) -> float:
    return math.radians(value)


def _clamp_axis(name: str, value: Optional[float], limit: float) -> Optional[float]:
    """将单轴角度裁剪到安全限位内；越界时打印告警，便于发现脚本里写过头的值。"""
    if value is None:
        return None
    clamped = max(-limit, min(limit, value))
    if abs(value - clamped) > 1e-6:
        log(f"[LIMIT] {name}={value:.1f}° 超出安全限位 ±{limit:.0f}°，已裁剪为 {clamped:.1f}°")
    return clamped


def speed_level_for(deg_per_sec: float) -> int:
    """将角速度诉求映射到接口速度档位。

    用户要求所有动作一律跑最快档，因此无论传入多少角速度，
    统一返回最高速度档 MAX_SPEED_LEVEL(=2)。
    """
    return MAX_SPEED_LEVEL


def head_command(
    *,
    yaw: Optional[float] = None,
    pitch: Optional[float] = None,
    roll: Optional[float] = None,
    speed_deg_s: float = 45,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """构建单步四联头颈控制命令，角度单位为度。"""
    return {
        "type": "set_four_combine_motor_control",
        "params": {
            "control_yaw": yaw is not None,
            "yaw_angle": deg(yaw or 0.0),
            "control_roll": roll is not None,
            "roll_angle": deg(roll or 0.0),
            "control_pitch": pitch is not None,
            "pitch_angle": deg(pitch or 0.0),
            "control_chassis_move": False,
            "chassis_offset": 0.0,
            "control_chassis_rotate": False,
            "chassis_rotation": 0.0,
            "speed_level": speed_level_for(speed_deg_s),
            "timeout": timeout,
        },
    }


def head_sequence(steps: List[Dict[str, Any]], timeout: float = 45.0) -> Dict[str, Any]:
    """构建头颈多步动作序列；步骤角度单位为度，不包含任何底盘字段。"""
    return {
        "type": "four_dof_head_sequence",
        "params": {
            "angle_unit": "deg",
            "timeout": timeout,
            "sequence": steps,
        },
    }


def waypoint(*, yaw=None, roll=None, pitch=None, speed_level=1, timeout=10.0) -> Dict[str, Any]:
    """构建单个路点（多路点控制用），角度单位为度，转弧度后打包。

    所有角度在打包前自动裁剪到物理安全限位内（yaw±90 / pitch±18 / roll±30），
    避免下游电机限位拒绝整条路点序列（曾出现 pitch=30 导致 REJECTED 104）。
    速度档位：用户要求一律跑最快档，故忽略传入 speed_level，强制 MAX_SPEED_LEVEL。
    """
    yaw = _clamp_axis("yaw", yaw, YAW_LIMIT_DEG)
    roll = _clamp_axis("roll", roll, ROLL_LIMIT_DEG)
    pitch = _clamp_axis("pitch", pitch, PITCH_LIMIT_DEG)
    return {
        "control_yaw": yaw is not None,
        "yaw_angle": deg(yaw) if yaw is not None else 0.0,
        "control_roll": roll is not None,
        "roll_angle": deg(roll) if roll is not None else 0.0,
        "control_pitch": pitch is not None,
        "pitch_angle": deg(pitch) if pitch is not None else 0.0,
        "control_chassis_move": False,
        "chassis_offset": 0.0,
        "control_chassis_rotate": False,
        "chassis_rotation": 0.0,
        "speed_level": MAX_SPEED_LEVEL,
        "timeout": float(timeout),
    }


def head_waypoint_sequence(waypoints: List[Dict[str, Any]], pose_mode: int = 0, timeout: float = 60.0) -> Dict[str, Any]:
    """构建多路点头颈控制命令（使用 set_four_combine_waypoint_control）。

    Args:
        waypoints: 路点列表，每个路点包含 control_*/angle/speed_level/timeout
        pose_mode: 0=相对位姿（缺省），1=绝对位姿
        timeout: Agent 等待全部路点执行完成的总超时（秒）
    """
    return {
        "type": "set_four_combine_waypoint_control",
        "params": {
            "waypoints": waypoints,
            "pose_mode": pose_mode,
            "timeout": timeout,
        },
    }


# ========================
# 1.png / 2.png / 3.png 场景定义
# ========================
SCENARIOS = [
    {
        "id": 1,
        "category": "交互中 / 用户对话",
        "name": "用户移动位置时的视线跟踪",
        "description": (
            "用户从机器人正前方起身，走到机器人侧面继续提问。\n"
            "  头部: 俯仰0°→45°(低头), 水平0°→45°(左转), 同时平滑跟踪。\n"
            "  速度: 图片要求俯仰45°/s、水平45°/s，映射为 speed_level=1。\n"
            "  底盘: 保持静止，本脚本不下发底盘控制。"
        ),
        "command": head_command(yaw=45, pitch=45, speed_deg_s=45),
    },
    {
        "id": 2,
        "category": "行走/巡逻 / 在家庭中行走",
        "name": "绕行障碍物时的协同转向（仅头部）",
        "description": (
            "机器人遇到障碍物需要绕行，路径向右转弯。\n"
            "  头部: 提前向绕行方向右侧预转，水平0°→-45°，引导视线。\n"
            "  速度: 图片要求水平30°/s，映射为 speed_level=0。\n"
            "  底盘: 图片中底盘转向动作本次不测，不下发底盘控制。"
        ),
        "command": head_command(yaw=-45, speed_deg_s=30),
    },
    {
        "id": 3,
        "category": "行走/巡逻 / 在家庭中行走",
        "name": "巡逻中停至桌子识别记忆物品",
        "description": (
            "机器人巡逻途中检测到桌子，自主靠近并停稳，识别记忆桌面物品后恢复巡逻。\n"
            "  头部: 停稳后低头看桌面，再左/中/右/中扫描，识别完成后抬头回正。\n"
            "  序列: pitch 0°→15°；yaw 0°→45°→0°→-45°→0°；pitch 15°→0°。\n"
            "  速度: 图片要求俯仰15°/s、水平30°/s，映射为低速/中低速。\n"
            "  底盘: 接近/减速动作本次不测，不下发底盘控制。"
        ),
        "command": head_sequence([
            {"pitch": 15, "speed_deg_s": 15, "timeout": 20.0},
            {"yaw": 45, "pitch": 15, "speed_deg_s": 30, "timeout": 20.0},
            {"yaw": 0, "pitch": 15, "speed_deg_s": 30, "timeout": 20.0},
            {"yaw": -45, "pitch": 15, "speed_deg_s": 30, "timeout": 20.0},
            {"yaw": 0, "pitch": 15, "speed_deg_s": 30, "timeout": 20.0},
            {"yaw": 0, "pitch": 0, "roll": 0, "speed_deg_s": 45, "timeout": 20.0},
        ]),
    },
    {
        "id": 4,
        "category": "唤醒 / 静止状态被唤醒",
        "name": "声源在头部转角范围内",
        "description": (
            "机器人静止充电，用户站立在正前方45°范围内呼唤唤醒词。\n"
            "  头部: 快速转向声源，俯仰0°→45°，水平0°→45°，同时运动并锁定用户。\n"
            "  速度: 图片要求俯仰45°/s、水平45°/s，偏快速响应，映射为 speed_level=1。\n"
            "  底盘: 不介入，保持静止。"
        ),
        "command": head_command(yaw=45, pitch=45, speed_deg_s=45),
    },
    {
        "id": 5,
        "category": "唤醒 / 静止状态被唤醒",
        "name": "声源超出头部转角极限（仅头部）",
        "description": (
            "机器人静止背对用户，用户站在后方呼唤唤醒词。\n"
            "  头部: 优先锁定声源，俯仰0°→45°，水平0°→90°；随后回正。\n"
            "  速度: 图片要求俯仰45°/s、水平90°/s；回正水平45°/s。\n"
            "  底盘: 图片中的原地旋转本次不测，不下发底盘控制。"
        ),
        "command": head_sequence([
            {"yaw": 90, "pitch": 45, "speed_deg_s": 90, "timeout": 25.0},
            {"yaw": 0, "pitch": 0, "roll": 0, "speed_deg_s": 45, "timeout": 25.0},
        ]),
    },
    {
        "id": 6,
        "category": "唤醒 / 运动状态被唤醒",
        "name": "行走中侧方被唤醒（仅头部）",
        "description": (
            "机器人正在向前行走，用户坐在左侧呼唤唤醒词。\n"
            "  头部: 优先锁定声源，水平0°→45°；随后回正。\n"
            "  速度: 图片要求水平45°/s，映射为 speed_level=1。\n"
            "  底盘: 图片中的左转本次不测，不下发底盘控制。"
        ),
        "command": head_sequence([
            {"yaw": 45, "speed_deg_s": 45, "timeout": 20.0},
            {"yaw": 0, "roll": 0, "pitch": 0, "speed_deg_s": 45, "timeout": 20.0},
        ]),
    },
    {
        "id": 7,
        "category": "唤醒 / 运动状态被唤醒",
        "name": "行走中后方被唤醒并停止（仅头部）",
        "description": (
            "机器人巡逻中，用户坐在后方喊停并唤醒。\n"
            "  头部: 优先锁定后方声源，水平0°→90°；随后柔和回正。\n"
            "  速度: 图片要求水平90°/s；回正水平45°/s。\n"
            "  底盘: 图片中的减速/转向/停止本次不测，不下发底盘控制。"
        ),
        "command": head_sequence([
            {"yaw": 90, "speed_deg_s": 90, "timeout": 25.0},
            {"yaw": 0, "roll": 0, "pitch": 0, "speed_deg_s": 45, "timeout": 25.0},
        ]),
    },
    {
        "id": 10,
        "category": "拟人化表达 / 多路点组合",
        "name": "好奇观察 - 发现有趣物体",
        "description": (
            "机器人发现地面有趣的小物体，好奇地凑近端详，边低头边左右歪头打量，最后抬头回正。\n"
            "  动作: 低头偏左凑近 → 左歪头细看 → 右歪头换角度 → 抬头侧看 → 回正\n"
            "  拟人化: 每个路点 pitch+yaw+roll 同时发力，模拟人凑近端详时头部的连续倾斜+转向\n"
            "  5个路点，多轴同步"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=15, roll=10, pitch=14, speed_level=1, timeout=8.0),
            waypoint(yaw=25, roll=25, pitch=13, speed_level=0, timeout=8.0),
            waypoint(yaw=-25, roll=-25, pitch=14, speed_level=0, timeout=8.0),
            waypoint(yaw=-10, roll=-15, pitch=-8, speed_level=1, timeout=8.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=1, timeout=8.0),
        ], pose_mode=0, timeout=45.0),
    },
    {
        "id": 11,
        "category": "拟人化表达 / 多路点组合",
        "name": "左右观望 - 寻找用户",
        "description": (
            "用户呼叫后消失，机器人左右观望寻找，先快速大幅扫视，再带点抬头的细致确认。\n"
            "  动作: 左扫抬头 → 右大幅扫视 → 回中偏左确认 → 右侧轻歪确认 → 回正\n"
            "  拟人化: 扫视时配合抬头(pitch)与轻微歪头(roll)，模拟人四处张望的灵动感\n"
            "  5个路点，速度有快慢变化"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=50, roll=8, pitch=-10, speed_level=2, timeout=6.0),
            waypoint(yaw=-80, roll=-10, pitch=-8, speed_level=2, timeout=6.0),
            waypoint(yaw=35, roll=6, pitch=-6, speed_level=1, timeout=6.0),
            waypoint(yaw=-30, roll=-8, pitch=4, speed_level=0, timeout=8.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=1, timeout=8.0),
        ], pose_mode=0, timeout=45.0),
    },
    {
        "id": 12,
        "category": "拟人化表达 / 多路点组合",
        "name": "点头认可 - 理解用户指令",
        "description": (
            "用户下达指令后，机器人点头表示理解和认可，点头时带一点点轻微的左右转动更自然。\n"
            "  动作: 轻抬头 → 干脆低头 → 再抬头 → 轻点确认 → 回正\n"
            "  拟人化: 点头(pitch)为主，叠加极小幅 yaw/roll 让动作不机械，有轻重缓急\n"
            "  5个路点"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=4, pitch=-12, speed_level=1, timeout=5.0),
            waypoint(yaw=-3, pitch=15, speed_level=2, timeout=5.0),
            waypoint(yaw=4, pitch=-14, speed_level=1, timeout=5.0),
            waypoint(yaw=-2, roll=3, pitch=12, speed_level=0, timeout=6.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=1, timeout=5.0),
        ], pose_mode=0, timeout=35.0),
    },
    {
        "id": 13,
        "category": "拟人化表达 / 多路点组合",
        "name": "摇头拒绝 - 不赞同当前操作",
        "description": (
            "用户要求执行不安全操作，机器人干脆地摇头表示拒绝。\n"
            "  动作: 左甩+轻低 → 右大幅甩头 → 左大幅甩头 → 右甩 → 回正\n"
            "  拟人化: 摇头(yaw)为主，叠加极小幅 roll/pitch 让甩头有摆动惯性感，不死板\n"
            "  5个路点，多轴同步"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=35, roll=4, pitch=4, speed_level=2, timeout=6.0),
            waypoint(yaw=-65, roll=-6, pitch=2, speed_level=2, timeout=6.0),
            waypoint(yaw=65, roll=6, pitch=2, speed_level=2, timeout=6.0),
            waypoint(yaw=-35, roll=-4, pitch=3, speed_level=2, timeout=6.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=2, timeout=6.0),
        ], pose_mode=0, timeout=35.0),
    },
    {
        "id": 14,
        "category": "拟人化表达 / 多路点组合",
        "name": "疑惑思考 - 处理复杂问题",
        "description": (
            "收到复杂指令，机器人做出思考状态：微微抬头偏向一侧，左右小幅摆动并轻歪头。\n"
            "  动作: 抬头偏左歪 → 转向右上沉思 → 左上换角度想 → 轻点头(想通了) → 回正\n"
            "  拟人化: 每步 pitch+yaw+roll 同时小幅联动，模拟人思考时头部不自觉的微动\n"
            "  5个路点，多轴同步"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=12, roll=10, pitch=-14, speed_level=1, timeout=8.0),
            waypoint(yaw=-30, roll=-12, pitch=-10, speed_level=1, timeout=8.0),
            waypoint(yaw=22, roll=14, pitch=-12, speed_level=1, timeout=8.0),
            waypoint(yaw=-8, roll=-5, pitch=10, speed_level=2, timeout=6.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=2, timeout=6.0),
        ], pose_mode=0, timeout=42.0),
    },
    {
        "id": 15,
        "category": "拟人化表达 / 多路点组合",
        "name": "环顾四周 - 进入新环境巡视",
        "description": (
            "机器人进入新房间，环顾四周了解环境，视线在左右上下之间灵活游走。\n"
            "  动作: 左转抬头看高处 → 正前上方 → 右大幅转抬头 → 右下方查看 → 回正\n"
            "  拟人化: 大幅 yaw 扫视配合 pitch 抬头/低头与轻微 roll，模拟人巡视陌生环境\n"
            "  5个路点，覆盖左中右+上下"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=60, roll=10, pitch=-15, speed_level=2, timeout=8.0),
            waypoint(yaw=0, roll=0, pitch=-15, speed_level=2, timeout=8.0),
            waypoint(yaw=-80, roll=-12, pitch=-14, speed_level=2, timeout=8.0),
            waypoint(yaw=-40, roll=-8, pitch=15, speed_level=2, timeout=8.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=2, timeout=8.0),
        ], pose_mode=0, timeout=48.0),
    },
    {
        "id": 16,
        "category": "拟人化表达 / 多路点组合",
        "name": "惊讶反应 - 发现意外情况",
        "description": (
            "机器人检测到意外情况（如物体突然倒下），猛地抬头后仰并左右晃动，再缓缓回神。\n"
            "  动作: 猛抬头后仰偏左 → 右歪急看 → 左歪再看 → 缓慢低头回正\n"
            "  拟人化: pitch 急速抬头叠加 yaw/roll 大幅晃动，制造受惊一抖的效果，最后慢回正\n"
            "  4个路点，前快后慢"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=12, roll=10, pitch=-15, speed_level=2, timeout=4.0),
            waypoint(yaw=20, roll=28, pitch=-15, speed_level=2, timeout=4.0),
            waypoint(yaw=-20, roll=-28, pitch=-14, speed_level=2, timeout=4.0),
            waypoint(yaw=0, roll=0, pitch=8, speed_level=2, timeout=8.0),
        ], pose_mode=0, timeout=28.0),
    },
    {
        "id": 17,
        "category": "拟人化表达 / 多路点组合",
        "name": "专注倾听 - 用户长篇讲述",
        "description": (
            "用户正在讲述，机器人保持专注倾听姿态，偶尔微调头部角度表示关注。\n"
            "  动作: 微低头偏头凑近 → 轻左转细听 → 轻歪头点头 → 轻右转 → 回中保持\n"
            "  拟人化: 以小幅 pitch+yaw+roll 同步微动，模拟人倾听时不自觉的偏头与点头\n"
            "  5个路点，幅度小但有连贯生命感"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=6, roll=5, pitch=10, speed_level=1, timeout=6.0),
            waypoint(yaw=14, roll=8, pitch=8, speed_level=1, timeout=6.0),
            waypoint(yaw=8, roll=4, pitch=14, speed_level=1, timeout=6.0),
            waypoint(yaw=-12, roll=-6, pitch=8, speed_level=1, timeout=6.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=1, timeout=6.0),
        ], pose_mode=0, timeout=40.0),
    },
    {
        "id": 18,
        "category": "拟人化表达 / 多路点组合",
        "name": "扫描识别 - 多角度物体检测",
        "description": (
            "机器人对眼前物体进行多角度扫描识别，边转头边歪头变换观察角度。\n"
            "  动作: 左侧低头歪看 → 正前俯看 → 右侧低头歪看 → 右侧平视 → 抬头回正\n"
            "  拟人化: 每个观察角度都叠加 roll 歪头，模拟人换角度端详物体\n"
            "  5个路点，多轴同步"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=45, roll=14, pitch=14, speed_level=1, timeout=8.0),
            waypoint(yaw=0, roll=0, pitch=15, speed_level=1, timeout=8.0),
            waypoint(yaw=-45, roll=-14, pitch=14, speed_level=1, timeout=8.0),
            waypoint(yaw=-45, roll=-6, pitch=0, speed_level=1, timeout=8.0),
            waypoint(yaw=0, roll=0, pitch=-8, speed_level=1, timeout=8.0),
        ], pose_mode=0, timeout=50.0),
    },
    {
        "id": 19,
        "category": "拟人化表达 / 多路点组合",
        "name": "打招呼 - 友好迎接用户",
        "description": (
            "用户走近，机器人活泼地抬头打招呼，左右轻快摆头+歪头表示友好热情。\n"
            "  动作: 抬头扬起 → 左转右歪(俏皮) → 右转左歪(俏皮) → 轻点头致意 → 回正\n"
            "  拟人化: 抬头同时左右摆头并反向歪头，模拟人热情打招呼的灵动\n"
            "  5个路点，轻快速度"
        ),
        "command": head_waypoint_sequence([
            waypoint(yaw=0, roll=0, pitch=-15, speed_level=2, timeout=6.0),
            waypoint(yaw=20, roll=-12, pitch=-12, speed_level=2, timeout=6.0),
            waypoint(yaw=-30, roll=14, pitch=-12, speed_level=2, timeout=6.0),
            waypoint(yaw=8, roll=-4, pitch=10, speed_level=1, timeout=6.0),
            waypoint(yaw=0, roll=0, pitch=0, speed_level=1, timeout=8.0),
        ], pose_mode=0, timeout=40.0),
    },
    {
        "id": 90,
        "category": "辅助",
        "name": "头部电机回归0位",
        "description": "将 yaw、pitch、roll 都回归到0°，不控制底盘。",
        "command": head_command(yaw=0, pitch=0, roll=0, speed_deg_s=45),
    },
    {
        "id": 99,
        "category": "手动输入控制",
        "name": "4自由度头颈手动控制（输入roll/pitch/yaw角度）",
        "description": (
            "手动输入头颈三轴角度（单位：度），转换为弧度后下发控制。\n"
            "  留空=不控制该轴；输入0=控制该轴回正。\n"
            "  本手动控制同样不下发底盘控制。"
        ),
        "command": None,
        "interactive": "head_4dof",
        "run_in_all": False,
    },
]


def input_optional_float(prompt: str) -> Optional[float]:
    """读取可选浮点数；留空表示不控制该轴。"""
    while True:
        val = input(prompt).strip()
        if val == "":
            return None
        try:
            return float(val)
        except ValueError:
            print("  输入无效，请输入数字或直接回车跳过")


def input_float(prompt: str, default: float = 0.0) -> float:
    try:
        val = input(prompt).strip()
        if val == "":
            return default
        return float(val)
    except ValueError:
        print("  输入无效，使用默认值:", default)
        return default


def build_head_4dof_command() -> Optional[Dict[str, Any]]:
    """交互式构建4自由度头颈控制命令。"""
    print("  ── 4自由度头颈参数输入 ──")
    yaw_deg = input_optional_float("    yaw偏航角(度, 正=左转, 负=右转, 留空=不控制): ")
    pitch_deg = input_optional_float("    pitch俯仰角(度, 正=低头, 负=抬头, 留空=不控制): ")
    roll_deg = input_optional_float("    roll翻滚角(度, 正=左歪, 负=右歪, 留空=不控制): ")
    speed_deg_s = input_float("    期望头部速度(°/s, 30/45/90; 默认45): ", 45.0)

    if yaw_deg is None and pitch_deg is None and roll_deg is None:
        print("  未输入任何轴，跳过")
        return None

    command = head_command(yaw=yaw_deg, pitch=pitch_deg, roll=roll_deg, speed_deg_s=speed_deg_s)
    params = command["params"]
    print(
        "  → "
        f"yaw={yaw_deg if yaw_deg is not None else '不控制'}, "
        f"pitch={pitch_deg if pitch_deg is not None else '不控制'}, "
        f"roll={roll_deg if roll_deg is not None else '不控制'}, "
        f"speed_level={params['speed_level']}"
    )
    return command


def command_has_chassis_control(command: Optional[Dict[str, Any]]) -> bool:
    """防止场景误带底盘控制字段。"""
    if not command:
        return False
    params = command.get("params", {})
    if params.get("control_chassis_move") or params.get("control_chassis_rotate"):
        return True
    for step in params.get("sequence", []):
        if step.get("control_chassis_move") or step.get("control_chassis_rotate"):
            return True
        if "chassis_offset" in step or "chassis_rotation" in step:
            return True
    return False


async def send_and_recv(websocket, command: Dict[str, Any], timeout: float = 90.0) -> Optional[Dict[str, Any]]:
    """发送命令并等待响应。

    多路点命令自动延长超时：从 params.timeout 提取 agent 超时，加 15s buffer。
    """
    # 如果是多路点命令，自动根据其内部 timeout 调整等待窗口
    if command.get("type") == "set_four_combine_waypoint_control":
        agent_timeout = command.get("params", {}).get("timeout", 60.0)
        timeout = max(timeout, agent_timeout + 15.0)
        log(f"  多路点命令，agent_timeout={agent_timeout:.0f}s，等待窗口={timeout:.0f}s")

    msg = json.dumps(command, ensure_ascii=False)
    log(f"  发送: {msg[:200]}..." if len(msg) > 200 else f"  发送: {msg}")
    start = time.time()

    try:
        await websocket.send(msg)
        log(f"  等待 Agent 响应（超时 {timeout:.0f}s）...")
        response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
        elapsed = time.time() - start
        resp_data = json.loads(response)
        log(f"  ← 收到响应 (耗时{elapsed:.2f}s): {json.dumps(resp_data, ensure_ascii=False, indent=2)}")
        return resp_data
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        log(f"  ✗ 等待响应超时（{timeout:.0f}s，已等待{elapsed:.0f}s）")
        return None
    except Exception as e:
        elapsed = time.time() - start
        log(f"  ✗ 通信异常（{elapsed:.2f}s）: {e}")
        return None


def response_success(resp: Dict[str, Any]) -> bool:
    """兼容 WebSocket 的 success 字段和 agent 内部 result 布尔字段。"""
    if "success" in resp:
        return bool(resp.get("success"))
    if isinstance(resp.get("result"), bool):
        return bool(resp.get("result"))
    return False


def print_scenario_menu() -> None:
    print("\n" + "=" * 80)
    print("  4自由度头颈控制 · 场景测试（含拟人化多路点组合动作）")
    print("=" * 80)

    current_category = None
    for s in SCENARIOS:
        if s["category"] != current_category:
            current_category = s["category"]
            print(f"\n  【{current_category}】")
        print(f"    {s['id']}. {s['name']}")

    print("\n    0. 全部运行（跳过手动输入场景）")
    print("    q. 退出")
    print("=" * 80)


async def run_scenario(websocket, scenario: Dict[str, Any]) -> bool:
    print(f"\n{'━' * 80}")
    print(f"  场景{scenario['id']}: {scenario['name']}")
    print(f"  分类: {scenario['category']}")
    print(f"{'─' * 80}")
    print(f"  {scenario['description']}")
    print(f"{'─' * 80}")

    interactive = scenario.get("interactive")
    if interactive == "head_4dof":
        command = build_head_4dof_command()
    else:
        command = scenario.get("command")

    if command is None:
        log("  跳过（无操作参数）")
        return True

    if command_has_chassis_control(command):
        log("  ✗ 场景包含底盘控制字段，已阻止下发")
        return False

    resp = await send_and_recv(websocket, command)
    if resp is None:
        log(f"  ✗ 场景{scenario['id']}测试失败: 无响应")
        return False

    success = response_success(resp)
    if success:
        log(f"  ✓ 场景{scenario['id']}测试通过")
    else:
        log(f"  ✗ 场景{scenario['id']}测试失败: {resp.get('error_msg', '未知错误')}")
    return success


async def main(ws_uri: str) -> None:
    while True:
        print_scenario_menu()
        choice = input("\n请选择场景编号: ").strip()

        if choice.lower() == "q":
            log("退出测试")
            break

        if choice == "0":
            selected = [s for s in SCENARIOS if s.get("run_in_all", True) and not s.get("interactive")]
        else:
            try:
                idx = int(choice)
                selected = [s for s in SCENARIOS if s["id"] == idx]
                if not selected:
                    print(f"  ✗ 无效编号: {idx}")
                    continue
            except ValueError:
                print("  ✗ 请输入数字或 'q'")
                continue

        log(f"连接到 {ws_uri} ...")
        try:
            async with websockets.connect(ws_uri) as websocket:
                log("✓ 已连接到WebSocket服务器")

                passed = 0
                failed = 0
                for scenario in selected:
                    success = await run_scenario(websocket, scenario)
                    passed += 1 if success else 0
                    failed += 0 if success else 1
                    if len(selected) > 1:
                        await asyncio.sleep(1.5)

                if len(selected) > 1:
                    print(f"\n{'━' * 80}")
                    log(f"测试汇总: 共 {len(selected)} 个场景, 通过 {passed}, 失败 {failed}")
                    print("━" * 80)

                log("关闭WebSocket连接...")
        except ConnectionRefusedError:
            log("✗ 无法连接到WebSocket服务器，请确保Agent已启动")
        except Exception as e:
            log(f"✗ 连接失败: {e}")

        log("返回场景菜单")
        if choice == "0":
            break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="4自由度头颈控制场景测试工具")
    parser.add_argument("--ws", default=DEFAULT_WS_URI, help=f"WebSocket地址，默认 {DEFAULT_WS_URI}")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print("4自由度头颈控制 · 场景测试工具")
    print("请确保以下服务已启动:")
    print("  1. SmartRobotAgent (WebSocket端口 8766)")
    print("  2. 四联组合电机控制下游/模拟节点 (/four_combine_motor_control_result)")
    print("  3. 本脚本只测头颈，不会下发底盘控制")
    print()
    print("新增功能:")
    print("  - ID 10-19: 拟人化多路点组合动作（好奇/观望/点头/摇头/思考/环顾等）")
    print("  - 使用 set_four_combine_waypoint_control 接口，支持 3-5 个路点序列")
    print("  - 多轴同步控制（yaw + roll + pitch），动作更自然流畅")
    print()
    asyncio.run(main(args.ws))
