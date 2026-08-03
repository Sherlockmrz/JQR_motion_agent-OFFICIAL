# Agent 最近若干条 Trace 评分

评分功能是电脑端按需运行的离线工具。平时不执行评分命令时，Agent 不会多开服务，也不会增加后台任务。

## 文件分工

机器人端更新以下 Agent 文件：

- `smart_robot_agent.py`
- `websocket_control_server.py`
- `config.py`

其中 `websocket_control_server.py` 会为同一 WebSocket 上收到的每条任务生成独立 Trace。找物和随后发送的 `stop_move` 不再共用一个 Trace。

电脑端保留以下评分文件，不需要上传到机器人：

- `agent_trace_scorer.py`
- `score_recent_agent_logs.ps1`

## 一、上传并重启 Agent

在电脑 PowerShell 中执行：

```powershell
cd C:\Users\rzma\Documents\GitHub\JQR_motion_agent-OFFICIAL

ssh sunrise@192.168.31.75 "mkdir -p /tmp/jqr_agent_update"
scp .\smart_robot_agent.py .\websocket_control_server.py .\config.py `
  sunrise@192.168.31.75:/tmp/jqr_agent_update/
```

进入机器人：

```bash
ssh sunrise@192.168.31.75
```

在机器人 SSH 中备份、安装并检查语法：

```bash
set -e
AGENT_DIR=/home/sunrise/jqr_deploy/JQR_20260722/agent
BACKUP_DIR="$AGENT_DIR/backup_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"
cd "$AGENT_DIR"
cp -a smart_robot_agent.py websocket_control_server.py config.py "$BACKUP_DIR"/
cp /tmp/jqr_agent_update/smart_robot_agent.py .
cp /tmp/jqr_agent_update/websocket_control_server.py .
cp /tmp/jqr_agent_update/config.py .
python3 -m py_compile smart_robot_agent.py websocket_control_server.py config.py
echo "Agent 文件安装完成，备份目录：$BACKUP_DIR"
```

杀掉全部旧 Agent，再启动一个新 Agent：

```bash
pkill -TERM -f '[s]mart_robot_agent.py' || true
sleep 3
pkill -KILL -f '[s]mart_robot_agent.py' || true
sleep 1

pgrep -af smart_robot_agent.py || true
ss -lntp | grep ':8766' || true

cd /home/sunrise/jqr_deploy/JQR_20260722/agent
chmod +x start_agent.sh
./start_agent.sh
sleep 3

pgrep -af smart_robot_agent.py
ss -lntp | grep ':8766'
ss -lntp | grep ':8001'
```

预期只有一个有效的 `smart_robot_agent.py` 进程，Agent 监听 `8766`，VLN 监听 `127.0.0.1:8001`。

实时看最新 Agent 日志：

```bash
AGENT_LOG=$(ls -1t /home/sunrise/jqr_deploy/JQR_20260722/agent/logs/agent/agent_*.log | head -n 1)
echo "$AGENT_LOG"
tail -F "$AGENT_LOG"
```

## 二、选择最近几条并评分

测试完成后，在电脑项目目录的 PowerShell 中执行：

```powershell
cd C:\Users\rzma\Documents\GitHub\JQR_motion_agent-OFFICIAL
powershell -ExecutionPolicy Bypass -File .\score_recent_agent_logs.ps1
```

脚本会要求输入机器人 SSH 密码，然后完成以下步骤：

1. 下载机器人目录中的全部 `agent_*.log` 到一个带时间戳的本地快照。
2. 找出所有包含“上层发来任务”的 Trace。
3. 询问本次要评分最近几条，直接回车默认 10 条。
4. 按任务开始时间排序，逐条打印所选 Trace 的完整日志和评分依据。
5. 保存前询问假阳性序号。
6. 最后询问是否保存 Markdown 报告。

数量选择提示示例：

```text
发现 37 条任务 Trace，要评分最近几条？输入 1-37（直接回车默认 10）：
```

例如输入 `5`，本次只展示和评分最新的 5 条；直接回车则选择最新 10 条。候选不足 10 条时，默认选择全部候选。

交互提示示例：

```text
评分检查：是否有假阳性？输入序号 1-5，多个用逗号分隔；没有则直接回车：
```

- 没有假阳性：直接按回车。
- 第 2、5 条是假阳性：输入 `2,5` 后回车。
- 假阳性会标记为 `FALSE_POSITIVE`，任务结果和执行效率均改为 0；执行证据和 Trace 闭环仍按日志评分。

最后会显示：

```text
是否保存本次评分报告？[Y/n]：
```

- 直接回车、输入 `y` 或 `1`：保存报告。
- 输入 `n` 或 `0`：不保存，只保留本次终端展示；不会生成 Markdown 文件。

报告自动保存到电脑：

```text
C:\Users\rzma\Documents\GitHub\JQR_motion_agent-OFFICIAL\agent_score_reports\agent_trace_score_YYYYMMDD_HHMMSS.md
```

下载的原始日志快照保存在：

```text
C:\Users\rzma\Documents\GitHub\JQR_motion_agent-OFFICIAL\agent_log_snapshots\YYYYMMDD_HHMMSS\
```

## 三、怎样确认确实是最近所选条数

报告开头会记录：扫描文件数、候选 Trace 总数、选择规则和实际评分条数。随后“最近任务清单”会列出每条的 Trace ID、开始时间、任务类型、来源日志文件。编号 `1` 是所选范围最早的一条，最后一个编号是最新一条。

每条详情还会记录来源文件、源文件首任务行号和评分窗口。评分窗口从该 Trace 第一条“上层发来任务”开始，到首次“结果已回复给客户端”结束；窗口后的后台日志会展示，但不参与评分。

旧版本 Agent 可能让找物和 `stop_move` 共用 Trace。如果一个 Trace 中出现多条“上层发来任务”，报告会按规则标为 `INVALID`。更新并重启 Agent 后，新任务会使用毫秒时间和序号组成的独立 Trace ID，例如：

```text
20260725-130058-513-000014
20260725-130058-521-000015
```

## 四、可选参数

机器人地址或日志目录变化时：

```powershell
powershell -ExecutionPolicy Bypass -File .\score_recent_agent_logs.ps1 `
  -RobotHost 192.168.31.75 `
  -RobotUser sunrise `
  -RemoteLogDir /home/sunrise/jqr_deploy/JQR_20260722/agent/logs/agent `
  -Limit 10
```

指定 `-Limit 10` 会跳过数量询问，直接评分最近 10 条；仍会询问假阳性和是否保存。不传 `-Limit` 才会交互选择数量。

已经有本地日志、不需要连接机器人时：

```powershell
python .\agent_trace_scorer.py `
  --log-dir .\agent_log_snapshots\YYYYMMDD_HHMMSS `
  --limit 10 `
  --output-dir .\agent_score_reports
```
