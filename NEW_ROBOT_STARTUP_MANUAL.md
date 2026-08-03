# JQR 新机器人启动手册

本文根据 2026-07-24 新机器人 `192.168.31.75` 的实际终端日志整理。新机 ROS 2 域为 `100`。地图、人脸、VLN client 和 Motion Agent 尚无完整的新机启动日志，相关步骤沿用旧机流程，并增加了启动前检查。

## 1. 当前结论

- 新机地址：`192.168.31.75`
- 用户：`sunrise`
- ROS 2 域：`ROS_DOMAIN_ID=100`
- 已确认入口：base 底盘、双目相机、四轴控制、融合里程计、Nav2
- 沿用旧入口：ASM 地图、地图服务、地图图像、人脸、VLN client、Motion Agent
- base 脚本不在 home 根目录，位于 `/home/sunrise/jqr_deploy/JQR_20260722/base_ws/start_base.sh`
- 未发现独立激光雷达启动命令。当前 Nav2 日志确认使用双目点云 `/StereoNetNode/stereonet_pointcloud2`

所有测试先清空机器人周围障碍物，并准备物理急停。当前 base 持续报告超声波读取失败，不能把超声波避障当作可用能力。

## 2. 每个终端的公共准备

在 Windows PowerShell 中，每开一个机器人终端先执行：

```powershell
ssh sunrise@192.168.31.75
```

登录机器人后执行：

```bash
export ROS_DOMAIN_ID=100
source /opt/ros/humble/setup.bash
echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
```

应输出 `ROS_DOMAIN_ID=100`。相机脚本会自行加载 TROS 环境，不要用 ROS 2 Humble 的环境替换脚本内部环境。

建议一个长期运行模块使用一个 SSH 终端。也可以在一个 SSH 连接中使用 `tmux` 分窗，但不要在前台进程运行时直接输入下一条启动命令。Agent 的 `start_agent.sh` 使用 `nohup` 后台启动，脚本返回后该终端可以继续使用。

## 3. 推荐启动顺序

严格按以下顺序启动：

1. base 底盘
2. 地瓜双目相机
3. 四轴电机控制器
4. 融合里程计与栅格映射
5. Nav2
6. ASM 地图、地图服务和地图图像订阅器
7. 人脸识别
8. VLN client
9. Motion Agent

### 3.1 终端 1：base 底盘

新机上有多个历史 base，其中本次 `JQR_20260722` 部署的正式入口是：

```bash
export ROS_DOMAIN_ID=100
cd /home/sunrise/jqr_deploy/JQR_20260722/base_ws
chmod +x start_base.sh
./start_base.sh
```

历史运行记录确认该入口启动的实际二进制和日志目录分别是：

```text
/home/sunrise/jqr_deploy/JQR_20260722/base_ws/install/jqr_base/lib/jqr_base/jqr_base_node
/home/sunrise/jqr_deploy/JQR_20260722/logs/base
```

不要使用以下旧版本或源码备份中的 `start_base.sh`：

```text
/home/sunrise/jqr_deploy/jqr_base_20260716/base_ws
/home/sunrise/jqr_deploy/JQR_20260722/base_source/jqr_ws
/home/sunrise/JQR_File/jqr_base_usb_base_*/jqr_base/jqr_ws
```

本次 `systemctl` 查询没有发现 JQR/base 开机服务，因此按上面的完整路径手动启动。`~/start_base.sh` 不存在，不能在 home 根目录直接执行。

base 运行检查：

```bash
ros2 node list | grep -Ei 'base|controller'
pgrep -af '/JQR_20260722/base_ws/install/jqr_base/lib/jqr_base/jqr_base_node'
fuser -v /dev/ttyACM0 2>&1 || true
ros2 topic info /odom -v
timeout 5 ros2 topic hz /odom
timeout 5 ros2 topic echo /head_motor_angle_feedback --once
```

日志中的 `Failed to get UltrasonicRecvDatafrom SDK` 表示超声波数据不可用，不等于 base 整体退出。Odom 和头部反馈仍在更新，说明主通信仍工作，但这是功能降级，不能忽略超声波相关安全风险。

### 3.2 终端 2：地瓜双目相机

```bash
cd ~
./start_digua_camera.sh
```

成功判据：

```text
StereoNetNode ... publish result ... fps: 29~30
```

另开检查终端执行：

```bash
export ROS_DOMAIN_ID=100
source /opt/ros/humble/setup.bash
ros2 topic list | grep StereoNetNode
timeout 8 ros2 topic hz /StereoNetNode/stereonet_pointcloud2
```

`nginx ... logs/error.log ... Permission denied` 不会阻止本次 ROS 相机和 StereoNet 发布；以点云是否持续约 30 Hz 为准。按 `Ctrl+C` 后出现的 `mipi_cam exit code -6` 是本次人工关闭阶段的输出，不是启动失败判据。

### 3.3 终端 3：四轴电机控制器

```bash
cd ~/dimensions_control
./start_on_s100p.sh
```

成功时应看到：

```text
First feedback on [four_motor_position_feedback]
First odom received on [odom]
First feedback received on [head_motor_angle_feedback]
```

检查：

```bash
timeout 5 ros2 topic echo /four_motor_position_feedback --once
timeout 5 ros2 topic echo /head_motor_angle_feedback --once
```

此终端必须保持运行。

### 3.4 终端 4：融合里程计与栅格映射

新机 home 中存在 `/home/sunrise/start_fusion_odom.sh`，且日志同时出现 `fusion_odom_node` 和 `grid_mapping_service`。启动命令因日志开头被顶掉，下面是根据现有脚本名与输出作出的高可信推断，尚需现场再确认一次：

```bash
cd ~
./start_fusion_odom.sh
```

成功判据：

```text
[fusion_odom_node] ... [STATE] ...
[grid_mapping_service]: [状态] 已处理: ..., 无位姿跳过: 0, 无深度跳过: 0
```

检查：

```bash
ros2 node list | grep -E 'fusion_odom|grid_mapping'
ros2 topic info /odom -v
timeout 8 ros2 topic hz /odom
timeout 5 ros2 run tf2_ros tf2_echo odom base_link
```

不要在 Nav2 运行期间关闭本终端。本次按 `Ctrl+C` 停止融合里程计后，Nav2 立即出现 pose delay、`getPose: false`、TF extrapolation 和 `nav exception: 303`。

### 3.5 终端 5：Nav2

确认前四项正常后执行：

```bash
cd ~/nav2
./start_on_s100p.sh
```

成功判据：controller、planner、recoveries 和 BT navigator 完成配置及激活，双目点云被订阅：

```text
Subscribed to Topics: depth_cloud
topic /StereoNetNode/stereonet_pointcloud2
Activating controller_server
Activating planner_server
```

检查：

```bash
ros2 node list | grep -E 'controller_server|planner_server|bt_navigator|manager_node'
timeout 8 ros2 topic hz /StereoNetNode/stereonet_pointcloud2
timeout 5 ros2 run tf2_ros tf2_echo odom base_link
```

`can not check version` 在本次日志中未阻止 Nav2 初始化，可先视为非致命告警。持续出现以下任意内容则导航未就绪：

```text
pose delay is too large
getPose: false
nav exception: 303
TF lookup ... extrapolation
```

出现这些错误时先恢复 fusion odom，不要直接发送找人找物任务。

### 3.6 终端 6：ASM 地图（沿用旧流程）

```bash
cd ~
bash start_asm_map.sh
```

检查：

```bash
ros2 topic list | grep -E 'asm|map'
```

### 3.7 终端 7：地图服务（沿用旧流程）

```bash
cd ~
bash start_map_service.sh
```

检查：

```bash
ros2 service list | grep -E 'GetMap|map'
```

### 3.8 终端 8：地图图像订阅器（需要看图时启动）

```bash
cd ~
bash get_map.sh
```

成功时应持续出现：

```text
订阅话题: /asm_map_image
保存图像: latest_asm_map.png
```

### 3.9 终端 9：人脸识别（沿用旧流程）

```bash
cd ~
bash launch_face_node.sh
```

检查：

```bash
pgrep -af jqr_face_ros2_node
ros2 service list | grep -E 'face_recognition|face_registration|face_delete'
```

至少应看到 `/face_recognition`。如果脚本提示节点已运行，先用上面的 `pgrep` 和 service 检查，不要重复启动。

### 3.10 终端 10：VLN client（沿用旧流程，端口改为 8001）

```bash
cd ~
export ROS_DOMAIN_ID=100
source /opt/ros/humble/setup.bash
source /home/sunrise/nav2/install/setup.bash
source /home/sunrise/asm-vln/map_server_ws/install/setup.bash
cd /home/sunrise/client_remote_bridge
python3 client_remote.py
```

启动前先验证 VLN client 能导入与当前 Nav2 一致的自定义 action：

```bash
ros2 pkg prefix nav2_msgs
python3 -c 'from nav2_msgs.action import NavigateToPose; print("nav2_msgs import OK")'
ros2 interface show nav2_msgs/action/NavigateToPose | head -n 30
```

`ros2 pkg prefix nav2_msgs` 应指向 `/home/sunrise/nav2/install/nav2_msgs`（或该工作空间内对应安装前缀），Python 应输出 `nav2_msgs import OK`。

如果出现 `ModuleNotFoundError: No module named 'nav2_msgs'`，说明 client 终端漏掉了：

```bash
source /home/sunrise/nav2/install/setup.bash
```

这套机器人使用自定义 `NavigateToPose` action。不要直接安装 Ubuntu apt 的标准 `ros-humble-nav2-msgs` 代替，否则可能与正在运行的 Nav2 action 定义不一致。

成功时应看到 ROS 2 数据源初始化，并成功连接 `/GetMap`、`/face_recognition`、图像和导航相关服务。另开检查终端执行：

```bash
pgrep -af client_remote.py
ss -lntp | grep ':8001'
```

本次系统统一使用：

```text
ws://127.0.0.1:8001/ws/navigate
```

如果 `8001` 没有监听，Motion Agent 的动态找人找物一定无法连接 VLN；先检查 client 终端原始报错。

### 3.11 终端 11：Motion Agent

此前板端检查确认部署目录为：

```text
/home/sunrise/jqr_deploy/JQR_20260722/agent
```

先确认新机也有该目录；如果部署日期不同，用 `find` 定位，不要退回 home 下可能过期的 `~/Jrobot_agent`：

```bash
if [ -d /home/sunrise/jqr_deploy/JQR_20260722/agent ]; then
  echo /home/sunrise/jqr_deploy/JQR_20260722/agent
else
  find /home/sunrise/jqr_deploy -maxdepth 3 -type f \
    -name start_agent.sh -printf '%T@ %h\n' 2>/dev/null | sort -nr
fi
```

如果输出了多个目录，选择本次明确部署的新版本，并先检查其中 `config.py`、`smart_robot_agent.py` 和 `websocket_control_server.py` 的修改时间。

先检查配置：

```bash
export AGENT_DIR=/home/sunrise/jqr_deploy/JQR_20260722/agent
cd "$AGENT_DIR"

grep -E '^(LOCAL_MODEL_URI|WEBSOCKET_HOST|WEBSOCKET_PORT)=' .env 2>/dev/null || true
grep -nE 'LOCAL_MODEL_URI|WEBSOCKET_HOST|WEBSOCKET_PORT' config.py
```

目标值为：

```text
LOCAL_MODEL_URI=ws://127.0.0.1:8001/ws/navigate
WEBSOCKET_HOST=0.0.0.0
WEBSOCKET_PORT=8766
```

先确认没有旧 Agent：

```bash
pgrep -af smart_robot_agent.py || true
ss -lntp | grep ':8766' || true
```

如需重启旧 Agent：

```bash
pkill -TERM -f '[s]mart_robot_agent.py' || true
sleep 2
pgrep -af smart_robot_agent.py || true
```

启动新 Agent：

```bash
export ROS_DOMAIN_ID=100
cd /home/sunrise/jqr_deploy/JQR_20260722/agent
chmod +x start_agent.sh
./start_agent.sh
```

检查：

```bash
pgrep -af smart_robot_agent.py
ss -lntp | grep ':8766'

AGENT_DIR=/home/sunrise/jqr_deploy/JQR_20260722/agent
LATEST_LOG=$(find "$AGENT_DIR/logs" -type f -name 'agent_*.log' \
  -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -n 1 | cut -d' ' -f2-)
echo "$LATEST_LOG"
tail -f "$LATEST_LOG"
```

成功时应看到 Agent 进程存在、`0.0.0.0:8766` 或 `*:8766` 正在监听。找人找物时 Agent 日志还应记录每一步 VLN 推理；只看到连接失败时回查 `8001`。

## 4. 全链路启动后总检查

在一个新的检查终端运行：

```bash
export ROS_DOMAIN_ID=100
source /opt/ros/humble/setup.bash

echo '========== DOMAIN =========='
echo "$ROS_DOMAIN_ID"

echo '========== PROCESSES =========='
pgrep -af 'jqr_base_node|base_controller|stereonet_model_node|mipi_cam|motor_controller_node|fusion_odom_node|grid_mapping_service|manager_node|jqr_face_ros2_node|client_remote.py|smart_robot_agent.py'

echo '========== PORTS =========='
ss -lntp | grep -E ':8001|:8766' || true

echo '========== SERVICES =========='
ros2 service list | grep -E 'GetMap|face_recognition|set_max_vel|GetObjectPosition' || true

echo '========== TOPICS =========='
ros2 topic list | grep -E 'odom|StereoNetNode/stereonet_pointcloud2|asm_map_image|four_motor_position_feedback|head_motor_angle_feedback'

echo '========== RATES =========='
timeout 8 ros2 topic hz /odom || true
timeout 8 ros2 topic hz /StereoNetNode/stereonet_pointcloud2 || true
```

只有 base、点云、融合位姿、Nav2、地图、人脸、VLN `8001` 和 Agent `8766` 全部正常后，才开始动态找人找物测试。

## 5. 当前需要团队补充确认的内容

1. `./start_fusion_odom.sh` 的原始输入行被顶掉了。脚本存在且输出吻合，但仍建议现场执行一次确认。
2. 新机日志没有独立激光雷达启动步骤。目前只能确认 Nav2 使用地瓜双目点云。
3. 地图、人脸、VLN client 和 Agent 是按旧流程迁移的命令，首次在 `192.168.31.75` 启动时要按本手册逐项记录结果。
