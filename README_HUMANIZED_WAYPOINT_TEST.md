# S100 头颈4自由度拟人化多路点测试 - 快速指南

## 更新内容

在 `test_4dof_head_control.py` 中新增 **10个拟人化多路点场景**（ID 10-19），使用 `set_four_combine_waypoint_control` 接口实现：

| ID | 场景名称 | 路点数 | 特点 |
|----|---------|--------|------|
| 10 | 好奇观察 - 发现有趣物体 | 4 | 低头+左右歪头端详，模拟好奇 |
| 11 | 左右观望 - 寻找用户 | 5 | 快速扫视+缓慢确认，速度有变化 |
| 12 | 点头认可 - 理解用户指令 | 5 | 抬头低头节奏，模拟认可 |
| 13 | 摇头拒绝 - 不赞同当前操作 | 4 | 左右摇头连贯动作 |
| 14 | 疑惑思考 - 处理复杂问题 | 4 | 抬头+左右摆动+歪头，多轴同步 |
| 15 | 环顾四周 - 进入新环境巡视 | 5 | 覆盖左中右+上下，全景扫描 |
| 16 | 惊讶反应 - 发现意外情况 | 4 | 快速后仰+晃动，前快后慢 |
| 17 | 专注倾听 - 用户长篇讲述 | 5 | 微小调整，速度极慢显示专注 |
| 18 | 扫描识别 - 多角度物体检测 | 5 | 多角度低头查看 |
| 19 | 打招呼 - 友好迎接用户 | 4 | 抬头+左右摆头，轻快友好 |

## S100 上运行测试

### 前提条件
1. **Agent 已启动**: `systemctl status agent` 或 `pgrep -af smart_robot_agent`
2. **WebSocket 8766 监听中**: Agent 默认绑定 `127.0.0.1:8766`
3. **下游控制节点就绪**: 真机控制节点或 mock 节点在运行

### 执行步骤

```bash
# SSH 登录 S100
ssh sunrise@192.168.31.75

# 进入部署目录
cd /home/sunrise/agent_head/Jrobot_agent

# 加载 ROS2 环境（如果 .bashrc 未自动 source）
source /opt/ros/humble/setup.bash
source install/setup.bash

# 运行测试脚本
python3 test_4dof_head_control.py
```

### 菜单操作

```
【拟人化表达 / 多路点组合】
  10. 好奇观察 - 发现有趣物体
  11. 左右观望 - 寻找用户
  12. 点头认可 - 理解用户指令
  13. 摇头拒绝 - 不赞同当前操作
  14. 疑惑思考 - 处理复杂问题
  15. 环顾四周 - 进入新环境巡视
  16. 惊讶反应 - 发现意外情况
  17. 专注倾听 - 用户长篇讲述
  18. 扫描识别 - 多角度物体检测
  19. 打招呼 - 友好迎接用户

  0. 全部运行（跳过手动输入场景）
  q. 退出
```

**输入场景编号**（如 `10`）运行单个场景，输入 `0` 批量运行所有场景（除手动输入场景）。

## 技术细节

### 多路点控制接口

```python
{
    "type": "set_four_combine_waypoint_control",
    "params": {
        "waypoints": [
            {
                "control_yaw": True,
                "yaw_angle": 0.785,  # 弧度
                "control_roll": False,
                "roll_angle": 0.0,
                "control_pitch": True,
                "pitch_angle": 0.524,
                "control_chassis_move": False,
                "chassis_offset": 0.0,
                "control_chassis_rotate": False,
                "chassis_rotation": 0.0,
                "speed_level": 1,
                "timeout": 8.0
            },
            # ... 更多路点
        ],
        "pose_mode": 0,  # 0=相对位姿（缺省），1=绝对位姿
        "timeout": 40.0  # Agent 等待全部路点完成的总超时
    }
}
```

### 自动超时适配

脚本的 `send_and_recv` 函数会自动根据多路点命令的 `params.timeout` 延长 WebSocket 等待窗口（+15s buffer），避免长序列超时。

### 响应格式

Agent 返回：
```json
{
    "success": true/false,
    "type": "set_four_combine_waypoint_control",
    "error_msg": "..." // 仅失败时
}
```

注意：`result` 字段在 agent 内部被 pop 掉，不会出现在 WebSocket 响应中。

## 预期效果

- **单场景执行**: 3-8秒/路点，总耗时约 20-60秒（视路点数和速度）
- **成功标志**: `✓ 场景XX测试通过`
- **失败情况**: 
  - Agent 未启动 → `✗ 无法连接到WebSocket服务器`
  - 下游未就绪 → 超时或 `error_msg`
  - 角度越限 → 下游拒绝，返回 `success: false`

## 调试技巧

### 查看 Agent 日志
```bash
tail -f /userdata/roslog/agent/agent_*.log
```

### 查看下游话题
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 topic list | grep -i four_combine
ros2 topic echo /four_combine_waypoint_control_result
```

### 手动触发单路点（验证下游）
在测试脚本菜单中选择 ID 1-9 的单步场景，或用 ID 90 回零。

## 常见问题

**Q: 场景执行后机器人没有动作？**
A: 检查下游控制节点是否在运行、电机是否使能、角度是否在安全范围内。

**Q: 响应超时？**
A: 多路点场景超时自动延长，但如果下游卡死或未订阅话题，仍会超时。检查 `/four_combine_waypoint_control` 是否有订阅者：
```bash
ros2 topic info /four_combine_waypoint_control
```

**Q: 想测试但没有真机？**
A: 启动 mock 节点模拟下游：
```bash
python3 mock_four_waypoint_node.py --mode progress
```

**Q: 角度越限被拒绝？**
A: 参考场景 ID 10-19 的角度范围（yaw ±90°, pitch ±30°, roll ±15°），修改 `waypoint()` 参数后重新部署。

## 文件清单

- `test_4dof_head_control.py` - 测试脚本（已更新，含 10 个新场景）
- `smart_robot_agent.py` - Agent 主程序（已在 S100 上运行）
- `mock_four_waypoint_node.py` - 下游模拟节点（仿真用）

## 下一步

1. 根据实际效果调整路点角度和速度
2. 添加更多拟人化场景（如疲倦/兴奋/警惕）
3. 结合底盘移动实现全身动作（修改 `chassis_offset`/`chassis_rotation`）
4. 记录用户偏好的动作序列，固化为预设

---

**版本**: v2.0 (2026-06-17)  
**更新**: 集成多路点拟人化场景，支持闭环测试
