# Sunrise MCU 新 SDK 部署与验收

## 1. 部署边界

仓库内的 `vendor/jqr_base/jqr_base_usb_base_20260716_185607.tar.gz` 保持原样。
不要在 Agent 仓库内直接解压后执行根目录 `colcon build`，因为压缩包和 Agent
都包含 `jqr_ros_msgs`，同一工作空间中出现两个同名 ROS 包会导致构建失败。

推荐布局：

```text
/app/jqr_ws/                  # 压缩包中的 Base 工作空间
/home/sunrise/Jrobot_agent/   # 本 Agent 仓库
```

## 2. 安装 Base 工作空间

在 Sunrise X3/X5（Ubuntu 22.04、aarch64、ROS 2 Humble）执行：

```bash
cd /home/sunrise/Jrobot_agent
sha256sum vendor/jqr_base/jqr_base_usb_base_20260716_185607.tar.gz
# 必须得到：
# AEE8BACA5F0CD5A8448411FDC429743DEF8AA506CB9D1AC05B7FA866C9D5B1BB

mkdir -p /tmp/jqr_base_deploy
tar -xzf vendor/jqr_base/jqr_base_usb_base_20260716_185607.tar.gz \
  -C /tmp/jqr_base_deploy

# 首次部署时 /app/jqr_ws 必须不存在；已有 Base 时先人工备份和确认版本。
sudo cp -a \
  /tmp/jqr_base_deploy/jqr_base_usb_base_20260716_185607/jqr_base/jqr_ws \
  /app/jqr_ws
sudo chown -R sunrise:sunrise /app/jqr_ws

source /opt/ros/humble/setup.bash
cd /app/jqr_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

Base 包只附带 `libSdkController_aarch64.so`，不能部署到 x86_64。确认
`/dev/ttyACM0` 存在且 `sunrise` 用户属于 `dialout` 组。

## 3. 构建 Agent

Agent 的 `jqr_ros_msgs` 是兼容上层人脸/相机接口的超集，同时加入了与 Base
逐字段一致的 `ClearFault`、`MedicineBoxCommand`、`MedicineBoxStatus`、
`StatusLightScene`、`StatusLightState`。

```bash
cd /home/sunrise/Jrobot_agent
source /opt/ros/humble/setup.bash
colcon build --symlink-install
chmod +x start_agent.sh sunrise_mcu_aux_test.sh
```

## 4. 启动顺序

终端 1：

```bash
source /opt/ros/humble/setup.bash
source /app/jqr_ws/install/setup.bash
ros2 launch jqr_base base_launch.py
```

确认服务：

```bash
ros2 node list
ros2 service list | grep -E 'clear_fault|medicine_box|status_light'
```

必须至少看到：

```text
/clear_fault
/set_medicine_box_command
/get_medicine_box_status
/set_medicine_box_switch
/get_medicine_box_state
/set_status_light_scene
/get_status_light_state
```

终端 2：

```bash
cd /home/sunrise/Jrobot_agent
JQR_BASE_WS=/app/jqr_ws ./start_agent.sh
```

## 5. 分级验收

无机械动作的安全检查：

```bash
cd /home/sunrise/Jrobot_agent
./sunrise_mcu_aux_test.sh
```

这会检查五个新服务、读取药箱/灯光状态，并验证白天 WORKING、WAITING 场景。

清故障会改变 MCU 状态，仅在恢复条件满足后执行：

```bash
JQR_ALLOW_FAULT_CLEAR=1 ./sunrise_mcu_aux_test.sh --clear-fault
```

药箱测试前必须清空机械区域并确认急停可用：

```bash
JQR_ALLOW_MECHANICAL_TEST=1 ./sunrise_mcu_aux_test.sh --mechanical
```

全部一起验收：

```bash
JQR_ALLOW_FAULT_CLEAR=1 JQR_ALLOW_MECHANICAL_TEST=1 \
  ./sunrise_mcu_aux_test.sh --clear-fault --mechanical
```

退出码 `0` 表示通过，`2` 表示服务不可用或 MCU 拒绝，`3` 表示状态无效、
动作故障或等待超时。

## 6. Motion Agent WebSocket 请求

以下请求发送到默认 `ws://机器人IP:8766`。灯光默认执行回读验证；药箱默认等待
与本次 `command_seq` 匹配的到位状态。

```json
{"type":"set_status_light_scene","params":{"scene":"working","ambient":"day","restart_pattern":true}}
{"type":"get_status_light_state","params":{}}
{"type":"set_medicine_box_command","params":{"command":"open","wait":true,"timeout":12}}
{"type":"get_medicine_box_status","params":{}}
{"type":"clear_fault","params":{"fault_mask":4294967295}}
```

旧请求仍可使用，但已经映射到新接口闭环：

```json
{"type":"set_robot_light_state","params":{"state":1}}
{"type":"set_medicine_box_switch","params":{"switch":true,"speed_stage":1}}
```

灯光旧参数 `state=1/2` 只是 `WORKING/WAITING` 的兼容别名，不是
`/get_status_light_state`。同一次设置请求不能同时提供旧 `state` 和新 `scene`；
查询服务与设置服务彼此独立，可以设置后立即查询。
