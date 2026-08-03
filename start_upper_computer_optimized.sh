#!/usr/bin/env bash
set -Eeuo pipefail

LOG_ROOT=${LOG_ROOT:-/userdata/roslog/onekey}
TS=${TS:-$(date +%Y%m%d_%H%M%S)}
RUN_DIR="$LOG_ROOT/$TS"
mkdir -p "$RUN_DIR"

BASE_PROC_PATTERN='/app/jqr_ws/install/jqr_base/lib/jqr_base/jqr_base_node'
CONTROL_PROC_PATTERN='/home/sunrise/dimensions_control/install/motor_controller/lib/motor_controller/motor_controller_node'
AGENT_PROC_PATTERN='python3 smart_robot_agent.py'

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$RUN_DIR/onekey.log"
}

show_file_tail() {
  local title="$1"
  local file="$2"
  local lines="${3:-120}"
  echo "===== $title: $file =====" | tee -a "$RUN_DIR/onekey.log"
  if [ -f "$file" ]; then
    tail -n "$lines" "$file" | tee -a "$RUN_DIR/onekey.log"
  else
    echo "log file not found: $file" | tee -a "$RUN_DIR/onekey.log"
  fi
}

extract_first_log_path() {
  local file="$1"
  local prefix_regex="$2"
  if [ ! -f "$file" ]; then
    return 0
  fi
  grep -Eo "${prefix_regex}[^[:space:]]*\.log" "$file" | tail -1 || true
}

extract_reported_log_after_marker() {
  local file="$1"
  local marker="$2"
  if [ ! -f "$file" ]; then
    return 0
  fi
  sed -n "s#.*${marker}[[:space:]]*##p" "$file" | awk '{print $1}' | grep -E '\.log$' | tail -1 || true
}

wait_for_file() {
  local file="$1"
  local timeout="${2:-5}"
  local i
  [ -z "$file" ] && return 1
  for ((i=1; i<=timeout; i++)); do
    [ -f "$file" ] && return 0
    sleep 1
  done
  return 1
}

latest_file() {
  local glob="$1"
  ls -t $glob 2>/dev/null | head -1 || true
}

fail_with_logs() {
  local msg="$1"
  shift || true
  log "ERROR: $msg"
  for item in "$@"; do
    [ -n "$item" ] && show_file_tail "failure log" "$item" 160
  done
  status_snapshot
  exit 1
}

run_step() {
  local name="$1"
  local dir="$2"
  local cmd="$3"
  local logfile="$RUN_DIR/${name}.log"
  log "STEP $name: cd $dir && $cmd"
  (
    cd "$dir"
    bash -lc "$cmd"
  ) > "$logfile" 2>&1
  local rc=$?
  if [ $rc -ne 0 ]; then
    log "STEP $name FAILED rc=$rc, startup_log=$logfile"
    return $rc
  fi
  log "STEP $name OK, startup_log=$logfile"
}

start_background_step() {
  local name="$1"
  local dir="$2"
  local cmd="$3"
  local logfile="$RUN_DIR/${name}.log"
  local pidfile="$RUN_DIR/${name}.pid"
  log "STEP $name: background cd $dir && $cmd"
  (
    cd "$dir"
    exec bash -lc "$cmd"
  ) > "$logfile" 2>&1 &
  local pid=$!
  echo "$pid" > "$pidfile"
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    log "STEP $name STARTED wrapper_pid=$pid, startup_log=$logfile"
  else
    log "STEP $name wrapper exited early, startup_log=$logfile"
  fi
}

has_proc() {
  pgrep -f "$1" >/dev/null 2>&1
}

proc_lines() {
  pgrep -af "$1" || true
}

wait_for_proc() {
  local label="$1"
  local pattern="$2"
  local timeout="${3:-15}"
  local i
  for ((i=1; i<=timeout; i++)); do
    if has_proc "$pattern"; then
      log "CHECK $label OK (found in ${i}s)"
      proc_lines "$pattern" | tee -a "$RUN_DIR/onekey.log"
      return 0
    fi
    sleep 1
  done
  log "CHECK $label FAILED: no process matched [$pattern] after ${timeout}s"
  return 1
}

# 优化版：智能稳定性检查
# - 如果进程已存在 >30s，跳过稳定性检查（假设已稳定）
# - 否则快速检查 3s（从 10s 降低）
wait_for_proc_stable() {
  local label="$1"
  local pattern="$2"
  local initial_timeout="${3:-15}"
  local stable_seconds="${4:-3}"  # 默认从 10s 降为 3s
  local i

  # 先检查进程是否存在
  if ! wait_for_proc "$label" "$pattern" "$initial_timeout"; then
    return 1
  fi

  # 智能判断：如果进程启动时间 > 30s，认为已稳定，跳过检查
  local pid
  pid=$(pgrep -f "$pattern" | head -1)
  if [ -n "$pid" ]; then
    local uptime_sec
    uptime_sec=$(ps -p "$pid" -o etimes= 2>/dev/null | tr -d ' ' || echo "0")
    if [ "$uptime_sec" -gt 30 ]; then
      log "CHECK $label SKIP stability: process already running ${uptime_sec}s (assumed stable)"
      return 0
    fi
  fi

  # 快速稳定性验证（3秒）
  log "CHECK $label: verifying stability for ${stable_seconds}s"
  for ((i=1; i<=stable_seconds; i++)); do
    sleep 1
    if ! has_proc "$pattern"; then
      log "CHECK $label FAILED: process exited at ${i}s"
      return 1
    fi
  done
  log "CHECK $label OK: stable for ${stable_seconds}s"
  return 0
}

wait_for_port() {
  local label="$1"
  local port="$2"
  local timeout="${3:-15}"
  local i
  for ((i=1; i<=timeout; i++)); do
    if ss -lnt 2>/dev/null | awk '{print $4}' | grep -qE "(^|:)${port}$"; then
      log "CHECK $label OK: port $port listening (${i}s)"
      return 0
    fi
    sleep 1
  done
  log "CHECK $label FAILED: port $port not listening after ${timeout}s"
  return 1
}

status_snapshot() {
  {
    echo "===== process snapshot ====="
    pgrep -af 'jqr_base_node|motor_controller_node|smart_robot_agent.py|test_4dof_head_control.py' || true
    echo
    echo "===== listening ports ====="
    ss -lntp 2>/dev/null | grep -E '8766|9000|8765' || true
    echo
    echo "===== latest agent logs ====="
    ls -lt /userdata/roslog/agent/agent_*.log 2>/dev/null | head -3 || true
    echo
    echo "===== latest base logs ====="
    ls -lt /userdata/roslog/base/base_*.log 2>/dev/null | head -3 || true
    echo
    echo "===== motor controller log ====="
    ls -l /home/sunrise/dimensions_control/tests/test_logs/motor_controller_node.log 2>/dev/null || true
    echo
    echo "===== onekey run dir ====="
    ls -la "$RUN_DIR"
  } | tee -a "$RUN_DIR/status.log"
}

start_prerequisites() {
  log "one-key upper-computer startup begin, run_dir=$RUN_DIR"

  # ======== make_net ========
  if ! run_step make_net /home/sunrise './make_net.sh'; then
    if ip addr show eth1 2>/dev/null | grep -q '192.168.137.100/24'; then
      log "CHECK make_net OK: eth1 configured (exit code ignored)"
    else
      fail_with_logs "make_net failed and eth1 not configured" "$RUN_DIR/make_net.log"
    fi
  fi
  if ! ip addr show eth1 2>/dev/null | grep -q '192.168.137.100/24'; then
    fail_with_logs "make_net verification failed: eth1 missing 192.168.137.100/24" "$RUN_DIR/make_net.log"
  fi
  log "CHECK make_net OK: eth1 has 192.168.137.100/24"

  # ======== jqr_base ========
  if has_proc "$BASE_PROC_PATTERN"; then
    log 'STEP start_base SKIP: jqr_base already running'
    proc_lines "$BASE_PROC_PATTERN" | tee -a "$RUN_DIR/onekey.log"
  else
    # 后台启动 base（避免卡住）
    start_background_step start_base /app/jqr_ws './start_base.sh'
    sleep 2  # 给 start_base.sh 时间初始化
  fi

  local base_runtime_log
  base_runtime_log=$(extract_reported_log_after_marker "$RUN_DIR/start_base.log" '日志:')
  [ -z "$base_runtime_log" ] && base_runtime_log=$(extract_first_log_path "$RUN_DIR/start_base.log" '/userdata/roslog/base/')
  [ -z "$base_runtime_log" ] && base_runtime_log=$(latest_file '/userdata/roslog/base/base_*.log')
  [ -n "$base_runtime_log" ] && log "CHECK base runtime log: $base_runtime_log"

  # 优化：快速稳定性检查（3s），已运行 >30s 则跳过
  if ! wait_for_proc_stable base "$BASE_PROC_PATTERN" 10 3; then
    fail_with_logs "base process unstable" "$RUN_DIR/start_base.log" "$base_runtime_log"
  fi

  # ======== motor_controller ========
  if has_proc "$CONTROL_PROC_PATTERN"; then
    log 'STEP start_on_s100p SKIP: motor_controller already running'
    proc_lines "$CONTROL_PROC_PATTERN" | tee -a "$RUN_DIR/onekey.log"
  else
    start_background_step start_on_s100p /home/sunrise/dimensions_control './start_on_s100p.sh'
  fi
  if ! wait_for_proc control "$CONTROL_PROC_PATTERN" 15; then
    fail_with_logs "motor_controller not started" "$RUN_DIR/start_on_s100p.log" '/home/sunrise/dimensions_control/tests/test_logs/motor_controller_node.log'
  fi
  sleep 2  # 给 motor_controller 初始化时间

  # ======== smart_robot_agent ========
  if has_proc "$AGENT_PROC_PATTERN"; then
    log 'STEP start_agent SKIP: agent already running'
    proc_lines "$AGENT_PROC_PATTERN" | tee -a "$RUN_DIR/onekey.log"
  else
    run_step start_agent /home/sunrise/agent_head/Jrobot_agent './start_agent.sh' || fail_with_logs "start_agent.sh failed" "$RUN_DIR/start_agent.log"
  fi

  local agent_runtime_log
  agent_runtime_log=$(extract_first_log_path "$RUN_DIR/start_agent.log" '/userdata/roslog/agent/')
  [ -z "$agent_runtime_log" ] && agent_runtime_log=$(latest_file '/userdata/roslog/agent/agent_*.log')

  if ! wait_for_proc agent "$AGENT_PROC_PATTERN" 15; then
    fail_with_logs "agent not started" "$RUN_DIR/start_agent.log" "$agent_runtime_log"
  fi
  if ! wait_for_port agent_ws 8766 15; then
    fail_with_logs "agent port 8766 not listening" "$RUN_DIR/start_agent.log" "$agent_runtime_log"
  fi
  log "CHECK agent OK, runtime log: ${agent_runtime_log:-unknown}"
}

run_test_foreground() {
  log "STEP test_4dof_head_control: launching interactive test"
  cd /home/sunrise/agent_head/Jrobot_agent
  python3 -u test_4dof_head_control.py
}

main() {
  start_prerequisites
  status_snapshot
  run_test_foreground
  log "one-key upper-computer startup finished"
}

case "${1:-start}" in
  start)
    main
    ;;
  status)
    status_snapshot
    ;;
  *)
    echo "Usage: $0 [start|status]"
    exit 2
    ;;
esac
