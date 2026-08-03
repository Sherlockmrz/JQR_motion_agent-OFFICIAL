#!/bin/bash

data_name=$(date +"%Y%m%d_%H%M%S")
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
agent_log_dir="${AGENT_LOG_DIR:-${script_dir}/logs/agent}"

if [ ! -d "${agent_log_dir}" ]; then
    mkdir -p "${agent_log_dir}"
fi

source /opt/ros/humble/setup.bash
cd "${script_dir}" || exit 1

if [ -f "${script_dir}/.env" ]; then
    set -a
    . "${script_dir}/.env"
    set +a
fi

jqr_base_ws="${JQR_BASE_WS:-/app/jqr_ws}"
if [ -f "${jqr_base_ws}/install/setup.bash" ]; then
    source "${jqr_base_ws}/install/setup.bash"
fi
source install/setup.bash

echo "Starting Smart Robot Agent, log: ${agent_log_dir}/agent_${data_name}.log"
nohup python3 smart_robot_agent.py >>"${agent_log_dir}/agent_${data_name}.log" 2>&1 &
echo "Agent started, PID: $!"
