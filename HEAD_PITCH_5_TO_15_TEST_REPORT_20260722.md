# Agent 控制头部前倾 5°～15°实体测试报告

## 1. 测试目的

本次测试用于验证交互系统通过 Agent 的 `forward_head` 功能控制机器人头部前倾时：

- Agent 是否能够正确接收并发送 0°、5°、10°和15°目标；
- 四轴位置反馈是否随前倾命令变化；
- 连续执行 `0° → 5° → 10° → 15°` 与从零位直接执行15°是否存在差异；
- 控制器当前 `0.02 rad` 到位阈值下的实际成功和失败情况。

## 2. 测试链路

```text
manual_forward_head_client.py
→ Smart Robot Agent WebSocket
→ /four_combine_motor_control
→ motor_controller_node
→ /four_motor_position_control
→ jqr_base_node
→ USB SDK / MCU
→ 头颈四轴电机
→ /four_motor_position_feedback
→ motor_controller_node
→ /combine_motor_control_result
→ Agent返回success/error_msg
```

本次使用中速档：

```text
turn_speed = 1
```

四轴反馈前四项的含义为：

```text
data[0] = neck_yaw
data[1] = neck_roll
data[2] = neck_pitch
data[3] = head_pitch
```

`data[4]`、`data[5]`为时间诊断信息，不是关节角度。

## 3. 当前完成阈值

测试前读取到四个关节的完成阈值均为：

```text
neck_yaw   = 0.02 rad
neck_roll  = 0.02 rad
neck_pitch = 0.02 rad
head_pitch = 0.02 rad
```

其中：

```text
0.02 rad ≈ 1.146°
```

当执行 `forward_head` 时，控制器会同时检查 `neck_pitch` 和 `head_pitch` 两个俯仰关节。两个关节都进入各自阈值并稳定满足控制器要求后，任务才返回101成功。

## 4. 测试过程和结果

### 4.1 初始回零：成功

Agent输入：

```json
{
  "type": "forward_head",
  "params": {
    "angle": 0.0,
    "turn_speed": 1
  }
}
```

Agent返回：

```json
{
  "success": true,
  "error_msg": "",
  "type": "forward_head"
}
```

四轴反馈：

```text
neck_yaw   =  0.00076699 rad ≈  0.044°
neck_roll  = -0.00191748 rad ≈ -0.110°
neck_pitch = -0.00249272 rad ≈ -0.143°
head_pitch =  0.01092961 rad ≈  0.626°
```

结果说明：两个俯仰物理关节的零位误差分别约为0.143°和0.626°，均小于1.146°阈值，因此回零任务成功。

### 4.2 从零位前倾5°：成功

Agent输入：

```json
{
  "type": "forward_head",
  "params": {
    "angle": 0.087266,
    "turn_speed": 1
  }
}
```

Agent返回：

```json
{
  "success": true,
  "error_msg": "",
  "type": "forward_head"
}
```

四轴反馈：

```text
neck_yaw   =  0.00076699 rad ≈  0.044°
neck_roll  = -0.00191748 rad ≈ -0.110°
neck_pitch =  0.08954613 rad ≈  5.131°
head_pitch =  0.01092961 rad ≈  0.626°
```

以控制器已确认的 `neck_priority` 分配方式估算，`neck_pitch`目标约为5°、`head_pitch`目标约为0°：

```text
neck_pitch误差 ≈ |5.131° - 5°| = 0.131°
head_pitch误差 ≈ |0.626° - 0°| = 0.626°
```

两项误差均小于1.146°，所以任务成功。

### 4.3 从5°继续前倾到10°：失败，但发生了实际运动

Agent输入：

```json
{
  "type": "forward_head",
  "params": {
    "angle": 0.174533,
    "turn_speed": 1
  }
}
```

Agent返回：

```json
{
  "success": false,
  "error_msg": "四联电机执行失败",
  "type": "forward_head"
}
```

四轴反馈：

```text
neck_yaw   =  0.00076699 rad ≈  0.044°
neck_roll  = -0.00191748 rad ≈ -0.110°
neck_pitch =  0.14572817 rad ≈  8.349°
head_pitch =  0.01092961 rad ≈  0.626°
```

机器人从约5.13°继续运动到了约8.35°，说明命令已经进入控制链并驱动了机械动作，但没有到达10°目标：

```text
neck_pitch目标 = 10°
neck_pitch实测 ≈ 8.349°
误差 ≈ 1.651° ≈ 0.02881 rad
```

该误差大于当前 `0.02 rad（1.146°）`阈值，因此这个结果符合控制器返回103的条件。此次不是“完全没有执行”，而是“执行了运动，但在完成等待时间内没有进入到位范围”。

### 4.4 在10°任务失败后继续发送15°：失败且位置未继续变化

Agent输入：

```json
{
  "type": "forward_head",
  "params": {
    "angle": 0.261799,
    "turn_speed": 1
  }
}
```

Agent返回：

```json
{
  "success": false,
  "error_msg": "四联电机执行失败",
  "type": "forward_head"
}
```

四轴反馈仍为：

```text
neck_yaw   =  0.00076699 rad ≈  0.044°
neck_roll  = -0.00191748 rad ≈ -0.110°
neck_pitch =  0.14572817 rad ≈  8.349°
head_pitch =  0.01092961 rad ≈  0.626°
```

与上一条10°失败后的反馈相同，说明这次15°命令没有使头部继续前倾。仅根据现有终端结果还不能确定它是被控制器状态拒绝、前一失败任务的停止/清理状态影响，还是发生了另一种103条件；需要对应任务的 `motor_controller_node` 日志才能进一步区分。

可以确定的是：`0° → 5° → 10° → 15°`这组连续递增测试没有完整通过。

### 4.5 失败后重新回零：成功

Agent输入：

```json
{
  "type": "forward_head",
  "params": {
    "angle": 0.0,
    "turn_speed": 1
  }
}
```

Agent返回：

```json
{
  "success": true,
  "error_msg": "",
  "type": "forward_head"
}
```

四轴反馈：

```text
neck_yaw   =  0.00076699 rad ≈  0.044°
neck_roll  = -0.00191748 rad ≈ -0.110°
neck_pitch =  0.00958738 rad ≈  0.549°
head_pitch =  0.01092961 rad ≈  0.626°
```

两个俯仰关节各自相对0°的误差均小于1.146°，所以控制器判定回零成功。

### 4.6 从零位直接前倾15°：成功

回零成功后，再次直接发送15°目标。

Agent输入：

```json
{
  "type": "forward_head",
  "params": {
    "angle": 0.261799,
    "turn_speed": 1
  }
}
```

Agent返回：

```json
{
  "success": true,
  "error_msg": "",
  "type": "forward_head"
}
```

四轴反馈：

```text
neck_yaw   =  0.00076699 rad ≈  0.044°
neck_roll  = -0.00191748 rad ≈ -0.110°
neck_pitch =  0.25368208 rad ≈ 14.535°
head_pitch =  0.01092961 rad ≈  0.626°
```

按照本次控制器使用的目标分配估算：

```text
neck_pitch目标 = 15°
neck_pitch误差 ≈ |15° - 14.535°| = 0.465°

head_pitch目标 = 0°
head_pitch误差 ≈ |0° - 0.626°| = 0.626°
```

两个物理关节误差均小于1.146°，所以本次直接15°动作返回成功。

两个俯仰关节的实测角度之和约为：

```text
14.535° + 0.626° = 15.161°
```

因此从整体头部姿态观察，本次实际总前倾约为15.16°，与15°目标非常接近。

## 5. 测试结果汇总

| 测试步骤 | Agent目标 | neck_pitch实测 | head_pitch实测 | 估算总俯仰 | Agent结果 |
|---|---:|---:|---:|---:|---|
| 初始回零 | 0° | -0.143° | 0.626° | 0.484° | 成功 |
| 从零位到5° | 5° | 5.131° | 0.626° | 5.757° | 成功 |
| 从5°继续到10° | 10° | 8.349° | 0.626° | 8.975° | 失败，返回103 |
| 10°失败后继续到15° | 15° | 8.349° | 0.626° | 8.975° | 失败，位置未继续变化 |
| 再次回零 | 0° | 0.549° | 0.626° | 1.176° | 成功 |
| 从零位直接到15° | 15° | 14.535° | 0.626° | 15.161° | 成功 |

## 6. 最终结论

1. Agent的 `forward_head` 输入、返回格式以及四轴控制链路均已实际工作。
2. 机器人可以从零位直接完成15°前倾，并由控制器返回101、Agent返回成功。
3. 机器人可以从零位完成5°前倾。
4. 本次没有完成 `5° → 10° → 15°`连续三级递增动作：10°阶段实际运动到约8.35°后返回103，随后发送15°时位置没有继续变化。
5. 10°失败时的 `neck_pitch`目标误差约为 `0.02881 rad（1.65°）`，超过当前 `0.02 rad（1.146°）`完成阈值，能够解释该次103。
6. 不能据此判断机器人“不能到15°”：回零后单次直接发送15°已经成功，实际总前倾约15.16°。
7. 当前问题更准确地描述为：单次前倾15°可以成功，但连续的5°、10°、15°分级目标执行不稳定；某一步返回103后，下一条前倾命令也可能不继续运动，回零后才恢复正常执行。
8. 要确定连续任务失败的最终原因，还需要对齐10°和随后15°两个任务的 `target_joints`、`joints_reached`、`post-trajectory settle timeout`等控制器日志。
