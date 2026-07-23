# 真机测试命令与期望结果

所有命令都在远端部署目录执行：

```bash
cd /home/sunrise/jqr_deploy/JQR_motion_agent_20260719
```

## 启动 jqr_base_node

终端 1：

```bash
source /opt/ros/humble/setup.bash
source base_ws/install/setup.bash
ros2 launch jqr_base base_launch.py
```

期望：节点保持运行，USB/MCU 初始化成功；另一个终端执行 `ros2 service list` 能看到
五个新 Service。若看不到 `/dev/ttyACM0`、出现 SDK 动态库错误或服务未注册，不能继续
机械测试。

## 默认安全验收

终端 2：

```bash
./tools/run_hardware_tests.sh
```

期望看到：

```text
FOUND   /clear_fault
FOUND   /set_medicine_box_command
FOUND   /get_medicine_box_status
FOUND   /set_status_light_scene
FOUND   /get_status_light_state
...
PASS: Sunrise MCU auxiliary acceptance test completed.
```

实际灯光效果：先切换到白天 WORKING，再切换到白天 WAITING；每次都要求 MCU
`accepted=true`，并通过 `/get_status_light_state` 回读到 `valid=true`、
`control_mode=2`、正确的 `scene` 和 `ambient=0`。最终停留在 WAITING。默认测试不移动
药箱、不清除故障。

## 单独查看状态

```bash
source /opt/ros/humble/setup.bash
source base_ws/install/setup.bash
python3 base_ws/src/jqr_base/scripts/mcu_aux_test.py status
```

药箱期望字段：`valid`、`state`、`target_command`、`command_source`、`io_flags`、
`fault_flags`、`current_ma`、`angle_raw`、`last_command_seq`、`last_result`。

药箱 `state`：0 未初始化、1 未知、2 已关闭、3 打开中、4 已打开、5 关闭中、
6 已停止、7 故障。

灯光期望字段：`valid`、`control_mode`、`scene`、`ambient`、`effect`、`flags`、
`last_command_seq`、`r/g/b/w_permille`。RGBW 数值仅用于诊断。

## 全部白天灯光场景

```bash
./tools/run_hardware_tests.sh --all-light-scenes
```

依次验证 OFF、WAITING、WORKING、SAFETY_ALERT、FAULT、ESTOP、LOW_BATTERY、
CRITICAL_BATTERY、CHARGING、UPGRADING、PAIRING，全部使用 `ambient=DAY` 和
`restart_pattern=true`。脚本最后重新设置 WAITING，避免机器人停在故障或急停灯效。

具体颜色、亮度、呼吸或闪烁节奏由 MCU 固件场景表决定；验收时既要观察实体灯，也要
确认回读的 `scene/effect/ambient` 一致。

## 清故障

确认物理故障恢复、急停释放、安全条件满足后：

```bash
JQR_ALLOW_FAULT_CLEAR=1 ./tools/run_hardware_tests.sh --clear-fault
```

期望 `result_number.data=1`，测试脚本退出码为 0。它只说明 MCU 接受并执行了清除请求；
仍存在的物理故障可能无法清除或再次出现。

## 药箱机械动作

先清空药箱机械区域并确认急停可用：

```bash
JQR_ALLOW_MECHANICAL_TEST=1 ./tools/run_hardware_tests.sh --mechanical
```

打开期望过程：ACK 的 `accepted=true` 并获得 `command_seq`；状态变为 OPENING(3)，
最后为 OPEN(4)。完成状态必须同时满足 `command_source=2`、序号匹配、
`target_command=1`、`fault_flags=0`。

关闭期望过程：状态变为 CLOSING(5)，最后为 CLOSED(2)；命令来源和序号仍必须匹配，
`target_command=2`、`fault_flags=0`。

STOP 期望：MCU 接受 STOP，药箱不再处于 OPENING/CLOSING。任何 `state=7`、
`fault_flags!=0` 或 12 秒超时都应当以退出码 3 报错，而不是误报成功。

## 启动 Agent 后测试上层调用链

先在 Agent 目录创建自己的 `.env`，不要从开发电脑上传密钥文件。然后：

```bash
cd agent
JQR_BASE_WS=/home/sunrise/jqr_deploy/JQR_motion_agent_20260719/base_ws ./start_agent.sh
```

通过 WebSocket 发送：

```json
{"type":"set_status_light_scene","params":{"scene":"working","ambient":"day","restart_pattern":true,"verify":true}}
{"type":"get_status_light_state","params":{}}
{"type":"set_medicine_box_command","params":{"command":"open","wait":true,"timeout":12}}
{"type":"get_medicine_box_status","params":{}}
{"type":"clear_fault","params":{"fault_mask":4294967295}}
```

上层成功返回应分别包含灯光的 `accepted=true, verified=true`、药箱的
`accepted=true, completed=true`，以及清故障的 `result_number=1`。

脚本退出码：0 通过；2 服务不可用、参数/安全开关错误或 MCU 拒绝；3 状态无效、
动作故障或等待超时。
