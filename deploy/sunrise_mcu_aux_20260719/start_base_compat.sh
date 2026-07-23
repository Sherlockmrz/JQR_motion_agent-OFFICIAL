#!/usr/bin/env bash

set -euo pipefail

script_path="$(readlink -f "${BASH_SOURCE[0]}")"
script_dir="$(cd "$(dirname "${script_path}")" && pwd)"
deploy_root="$(cd "${script_dir}/.." && pwd)"
base_ws="${JQR_BASE_WS:-${deploy_root}/base_ws}"
base_log_dir="${BASE_LOG_DIR:-${deploy_root}/logs/base}"
mcu_device="${JQR_USB_DEVICE:-/dev/ttyACM0}"
mcu_baudrate="${JQR_BAUDRATE:-115200}"
ros_domain_id="${ROS_DOMAIN_ID:-37}"

if [[ ! -f "${base_ws}/install/setup.bash" ]]; then
    echo "Base workspace is not built: ${base_ws}/install/setup.bash" >&2
    exit 2
fi

if [[ ! -e "${mcu_device}" ]]; then
    echo "MCU serial device is not available: ${mcu_device}" >&2
    echo "Connect the MCU first, or set JQR_USB_DEVICE to the correct path." >&2
    exit 2
fi

if pgrep -u "$(id -u)" -f '(^|/)(jqr_base_node)( |$)' >/dev/null 2>&1; then
    echo "jqr_base_node is already running; refusing to start a duplicate." >&2
    pgrep -a -u "$(id -u)" -f '(^|/)(jqr_base_node)( |$)' || true
    exit 3
fi

mkdir -p "${base_log_dir}"

source /opt/ros/humble/setup.bash
source "${base_ws}/install/setup.bash"

export ROS_DOMAIN_ID="${ros_domain_id}"
export JQR_USB_DEVICE="${mcu_device}"
export JQR_BAUDRATE="${mcu_baudrate}"
export LD_LIBRARY_PATH="${base_ws}/src/jqr_base/include/jqr_sdk_lib/lib/sdk_lib:${LD_LIBRARY_PATH:-}"

data_name="$(date +"%Y%m%d_%H%M%S")"
log_file="${base_log_dir}/base_${data_name}.log"

echo "Starting jqr_base"
echo "  workspace: ${base_ws}"
echo "  MCU device: ${JQR_USB_DEVICE}"
echo "  baudrate: ${JQR_BAUDRATE}"
echo "  ROS_DOMAIN_ID: ${ROS_DOMAIN_ID}"
echo "  log: ${log_file}"

nohup ros2 run jqr_base jqr_base_node "${base_log_dir}" \
    >>"${log_file}" 2>&1 &
base_pid=$!

sleep 2
if kill -0 "${base_pid}" 2>/dev/null; then
    echo "jqr_base started, PID: ${base_pid}"
else
    echo "jqr_base exited during startup. Latest log:" >&2
    tail -n 80 "${log_file}" >&2 || true
    exit 4
fi
