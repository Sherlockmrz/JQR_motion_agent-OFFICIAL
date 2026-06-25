#!/bin/bash

data_name=$(date +"%Y%m%d_%H%M%S")
agent_log_dir="/userdata/roslog/agent"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "${agent_log_dir}" ]; then
    mkdir -p "${agent_log_dir}"
fi

source /opt/ros/humble/setup.bash
cd "${script_dir}" || exit 1
source install/setup.bash

if [ -f "${script_dir}/.env" ]; then
    set -a
    . "${script_dir}/.env"
    set +a
fi

echo "Starting Smart Robot Agent, log: ${agent_log_dir}/agent_${data_name}.log"
nohup python3 smart_robot_agent.py >>"${agent_log_dir}/agent_${data_name}.log" 2>&1 &
echo "Agent started, PID: $!"
