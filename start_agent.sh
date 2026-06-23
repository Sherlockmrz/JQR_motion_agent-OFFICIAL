#!/bin/bash

data_name=$(date +"%Y%m%d_%H%M%S")
agent_log_dir="/userdata/roslog/agent"

if [ ! -d "${agent_log_dir}" ]; then
    mkdir -p "${agent_log_dir}"
fi

source /opt/ros/humble/setup.bash
source install/setup.bash

if [ -f ".env" ]; then
    set -a
    . ./.env
    set +a
fi

echo "Starting Smart Robot Agent, log: ${agent_log_dir}/agent_${data_name}.log"
nohup python3 smart_robot_agent.py >>"${agent_log_dir}/agent_${data_name}.log" 2>&1 &
echo "Agent started, PID: $!"
