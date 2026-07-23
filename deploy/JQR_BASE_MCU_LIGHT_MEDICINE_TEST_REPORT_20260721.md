# JQR Base MCU 状态灯与药箱真机测试报告

## 1. 测试信息

- 测试日期：2026-07-21
- 机器人地址：`sunrise@192.168.31.37`
- ROS 2：Humble
- `ROS_DOMAIN_ID`：`37`
- Base 工作空间：`/home/sunrise/jqr_deploy/JQR_20260720/base_ws`
- 测试脚本：`/home/sunrise/jqr_deploy/JQR_20260720/base_ws/src/jqr_base/scripts/mcu_aux_test.py`
- MCU USB：Artery AT32 Virtual COM Port，设备节点 `/dev/ttyACM0`
- 测试环境：白天模式，`ambient=0 (DAY)`

## 2. 测试结论

本次真机测试中，故障清除、药箱原生命令、药箱详细状态、状态灯场景控制和状态灯查询五个新 ROS 2 Service 均已注册。状态灯的 WAITING、WORKING、SAFETY_ALERT、FAULT、ESTOP、LOW_BATTERY、CRITICAL_BATTERY、CHARGING、UPGRADING、PAIRING 和 OFF 场景均获得 MCU ACK，MCU 回读的场景、昼夜模式及效果与下发命令匹配，测试脚本退出码均为 0。

药箱初始状态有效且无故障；打开命令由 CLOSED 经 OPENING 到达 OPEN，关闭命令由 OPEN 经 CLOSING 回到 CLOSED。两次动作的命令来源、目标命令和命令序号均匹配，动作期间及完成后 `fault=0x0000`，测试通过。

## 3. 新增 MCU Service 检查（全部可用）

执行检查后返回：

```text
[PASS] /clear_fault
[PASS] /set_medicine_box_command
[PASS] /get_medicine_box_status
[PASS] /set_status_light_scene
[PASS] /get_status_light_state
check退出码=0
```

已注册的相关服务包括：

```text
/clear_fault
/get_medicine_box_state
/get_medicine_box_status
/get_status_light_state
/set_medicine_box_command
/set_medicine_box_switch
/set_status_light_scene
```

其中 `/set_medicine_box_switch` 和 `/get_medicine_box_state` 是保留的旧兼容服务；本次新功能测试使用 `/set_medicine_box_command` 和 `/get_medicine_box_status`。

## 4. 初始状态：药箱关闭、状态指示灯熄灭（测试通过）

初始查询返回：

```text
medicine: valid=True state=2(CLOSED) target=0 source=0 seq=0 fault=0x0000 result=0 current=201mA angle_raw=0 io=0x0d
light: valid=True mode=0 scene=0(OFF) ambient=0 effect=0(OFF) seq=0 flags=0x01 rgbw=[0,0,0,0]
[PASS] medicine-box and status-light reports are valid
status退出码=0
```

结果说明：药箱状态有效，初始位置为关闭，无药箱故障；状态灯处于关闭模式，RGBW 输出全部为 0。

## 5. 工作状态指示灯：绿色、中亮度、常亮（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=2(WORKING) ambient=0 effect=1(STEADY) seq=209 flags=0x03 rgbw=[0,897,0,0]
[PASS] MCU reports the requested status-light scene
WORKING退出码=0
```

结果说明：MCU 接受 WORKING 场景；`mode=2` 表示场景控制，`ambient=0` 表示白天，`effect=1` 表示常亮；绿色通道输出为 897‰，其余通道为 0。

## 6. 待机状态指示灯：暖白色、低亮度、慢呼吸（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=1(WAITING) ambient=0 effect=3(BREATHE) seq=144 flags=0x03 rgbw=[0,0,0,946]
[PASS] MCU reports the requested status-light scene
WAITING测试退出码=0
```

后续状态中该场景的命令序号更新为 `seq=177`，白色通道快照为 817‰。呼吸场景的 RGBW 是查询瞬间的输出快照，因此会随呼吸相位变化。场景要求为暖白色低亮度呼吸，约 6 秒一个周期。

## 7. 紧急安全告警指示灯：红色、高亮度、快速闪烁（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=3(SAFETY_ALERT) ambient=0 effect=2(BLINK) seq=54 flags=0x03 rgbw=[1000,0,0,0]
[PASS] MCU reports the requested status-light scene
SAFETY_ALERT退出码=0
```

结果说明：红色通道输出为 1000‰，`effect=2` 表示闪烁；场景要求为约 0.5 秒一个闪烁周期。

## 8. 故障状态指示灯：红色、高亮度、常亮（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=4(FAULT) ambient=0 effect=1(STEADY) seq=122 flags=0x03 rgbw=[1000,0,0,0]
[PASS] MCU reports the requested status-light scene
FAULT退出码=0
```

结果说明：MCU 回读为 FAULT，红色通道 1000‰，灯效为常亮。

## 9. 急停状态指示灯：红色、高亮度、常亮（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=5(ESTOP) ambient=0 effect=1(STEADY) seq=199 flags=0x03 rgbw=[1000,0,0,0]
[PASS] MCU reports the requested status-light scene
ESTOP退出码=0
```

结果说明：MCU 回读为 ESTOP，红色通道 1000‰，灯效为常亮。FAULT 和 ESTOP 的实体显示相同，但回读的业务场景分别为 4 和 5。

## 10. 常规低电指示灯：黄色、中亮度、慢闪（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=6(LOW_BATTERY) ambient=0 effect=2(BLINK) seq=41 flags=0x03 rgbw=[950,850,0,0]
[PASS] MCU reports the requested status-light scene
LOW_BATTERY退出码=0
```

结果说明：红、绿通道组合为黄色，`effect=2` 表示闪烁；场景要求为约 2 秒一个闪烁周期。

## 11. 深度低电指示灯：黄色、中亮度、较快闪烁（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=7(CRITICAL_BATTERY) ambient=0 effect=2(BLINK) seq=111 flags=0x03 rgbw=[950,850,0,0]
[PASS] MCU reports the requested status-light scene
CRITICAL_BATTERY退出码=0
```

结果说明：红、绿通道组合为黄色；场景要求为约 1 秒一个闪烁周期，比常规低电闪烁更快。

## 12. 充电状态指示灯：绿色、低亮度、呼吸（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=8(CHARGING) ambient=0 effect=3(BREATHE) seq=124 flags=0x03 rgbw=[0,765,0,0]
[PASS] MCU reports the requested status-light scene
CHARGING退出码=0
```

另一查询瞬间绿色通道为 832‰。变化来自呼吸相位。场景要求为绿色低亮度呼吸，约 2 秒一个周期。

## 13. 升级状态指示灯：蓝色、中亮度、呼吸（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=9(UPGRADING) ambient=0 effect=3(BREATHE) seq=161 flags=0x03 rgbw=[0,0,808,0]
[PASS] MCU reports the requested status-light scene
UPGRADING退出码=0
```

结果说明：蓝色通道输出快照为 808‰，灯效为呼吸；场景要求为约 2 秒一个呼吸周期。

## 14. 配对状态指示灯：蓝色、中亮度、闪烁（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=10(PAIRING) ambient=0 effect=2(BLINK) seq=198 flags=0x03 rgbw=[0,0,950,0]
[PASS] MCU reports the requested status-light scene
PAIRING退出码=0
```

结果说明：蓝色通道输出为 950‰，灯效为闪烁；场景要求为约 2 秒一个闪烁周期。

## 15. 关闭状态指示灯：灯光熄灭（测试通过）

MCU 返回：

```text
light ACK: accepted=True message=Status light scene acknowledged by MCU
light: valid=True mode=2 scene=0(OFF) ambient=0 effect=0(OFF) seq=247 flags=0x03 rgbw=[0,0,0,0]
[PASS] MCU reports the requested status-light scene
OFF退出码=0
```

结果说明：场景回到 OFF，灯效为 OFF，RGBW 四个通道均为 0，测试结束后状态灯已关闭。

## 16. 药箱初始动作状态：已关闭、无故障（测试通过）

动作前返回：

```text
medicine: valid=True state=2(CLOSED) target=0 source=0 seq=0 fault=0x0000 result=0 current=-131mA angle_raw=0 io=0x0d
light: valid=True mode=2 scene=0(OFF) ambient=0 effect=0(OFF) seq=247 flags=0x03 rgbw=[0,0,0,0]
[PASS] medicine-box and status-light reports are valid
初始状态退出码=0
```

结果说明：药箱状态有效，位于关闭位置，当前没有动作目标和命令来源，故障位为 0。

## 17. 药箱打开动作：由关闭经过打开中到达完全打开（测试通过）

MCU ACK 和主要状态变化：

```text
medicine ACK: accepted=True seq=241 message=Medicine box command acknowledged by MCU
medicine: valid=True state=2(CLOSED) target=0 source=0 seq=0 fault=0x0000 result=0 current=-192mA angle_raw=0 io=0x0d
medicine: valid=True state=3(OPENING) target=1 source=2 seq=241 fault=0x0000 result=0 current=70mA angle_raw=685 io=0x0d
medicine: valid=True state=3(OPENING) target=1 source=2 seq=241 fault=0x0000 result=0 current=536mA angle_raw=7636 io=0x0c
medicine: valid=True state=4(OPEN) target=1 source=2 seq=241 fault=0x0000 result=1 current=122mA angle_raw=8434 io=0x0c
[PASS] matching MCU completion status received
打开药箱退出码=0
```

完成后再次查询：

```text
medicine: valid=True state=4(OPEN) target=1 source=2 seq=241 fault=0x0000 result=1 current=-80mA angle_raw=8434 io=0x0c
[PASS] medicine-box and status-light reports are valid
```

结果说明：

- `accepted=True`：MCU 接受打开命令；
- `source=2`：命令来源为 HOST；
- ACK 与状态中的命令序号均为 241；
- `target=1`：动作目标为 OPEN；
- 状态由 `CLOSED(2)` 进入 `OPENING(3)`，最终到达 `OPEN(4)`；
- 最终 `result=1`，动作完成；
- 全程 `fault=0x0000`，未发生药箱故障。

## 18. 药箱关闭动作：由打开经过关闭中回到完全关闭（测试通过）

MCU ACK 和主要状态变化：

```text
medicine ACK: accepted=True seq=152 message=Medicine box command acknowledged by MCU
medicine: valid=True state=4(OPEN) target=1 source=2 seq=241 fault=0x0000 result=1 current=-231mA angle_raw=8434 io=0x0c
medicine: valid=True state=5(CLOSING) target=2 source=2 seq=152 fault=0x0000 result=0 current=256mA angle_raw=10953 io=0x0c
medicine: valid=True state=5(CLOSING) target=2 source=2 seq=152 fault=0x0000 result=0 current=450mA angle_raw=173 io=0x0c
medicine: valid=True state=2(CLOSED) target=2 source=2 seq=152 fault=0x0000 result=1 current=-92mA angle_raw=2263 io=0x0d
[PASS] matching MCU completion status received
关闭药箱退出码=0
```

完成后再次查询：

```text
medicine: valid=True state=2(CLOSED) target=2 source=2 seq=152 fault=0x0000 result=1 current=-210mA angle_raw=2263 io=0x0d
[PASS] medicine-box and status-light reports are valid
```

结果说明：

- `accepted=True`：MCU 接受关闭命令；
- `source=2`：命令来源为 HOST；
- ACK 与动作状态中的命令序号均为 152；
- `target=2`：动作目标为 CLOSE；
- 状态由 `OPEN(4)` 进入 `CLOSING(5)`，最终回到 `CLOSED(2)`；
- 最终 `result=1`，动作完成；
- 全程 `fault=0x0000`，未发生药箱故障。

命令序号是 `uint8`，可以循环回绕，因此关闭命令的 152 小于打开命令的 241 并不代表异常；判断动作是否匹配，应比较每次 ACK 返回的序号与该次状态回读序号是否相等。

## 19. 最终结论及未覆盖项

本次终端结果证明以下链路已经正常工作：

```text
ROS 2 Client
→ jqr_base_node
→ JQR USB SDK
→ USB CDC (/dev/ttyACM0)
→ MCU
→ 状态回读
```

已经完成并通过：

1. 五个新 MCU Service 的注册与可用性检查；
2. 状态灯全部业务场景的白天模式下发、ACK 和 MCU 状态回读；
3. 状态灯 RGBW 输出通道与场景颜色对应；
4. 药箱打开动作及最终到位检查；
5. 药箱关闭动作及最终到位检查；
6. 药箱动作命令来源、目标、序号、结果和故障位检查。

本次终端记录没有包含以下真实功能测试，因此不能写成已经验证：

1. `/clear_fault` 对一个实际存在且恢复条件已经满足的故障进行清除；当前只验证了该 Service 可用；
2. 药箱运动过程中的 STOP 中止动作；
3. 状态灯夜间模式；
4. 状态灯周期的仪器计时数据。终端确认了 BLINK/BREATHE 效果类型，具体 0.5 秒、1 秒、2 秒和 6 秒周期来自产品要求及现场观察项。

