#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
remote_root="$(cd "${script_dir}/.." && pwd)"
base_ws="${JQR_BASE_WS:-${remote_root}/base_ws}"
agent_ws="${JQR_AGENT_WS:-${remote_root}/agent}"
clear_fault=false
mechanical=false
all_light_scenes=false

usage() {
    cat <<'EOF'
Usage: run_hardware_tests.sh [--clear-fault] [--mechanical] [--all-light-scenes]

Default: service discovery, state reads, DAY WORKING and DAY WAITING verification.
--clear-fault: clear 0xffffffff; also requires JQR_ALLOW_FAULT_CLEAR=1.
--mechanical: OPEN, CLOSE and STOP tests; also requires JQR_ALLOW_MECHANICAL_TEST=1.
--all-light-scenes: verify all documented DAY scenes, ending in WAITING.
EOF
}

for arg in "$@"; do
    case "${arg}" in
        --clear-fault) clear_fault=true ;;
        --mechanical) mechanical=true ;;
        --all-light-scenes) all_light_scenes=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: ${arg}" >&2; usage >&2; exit 2 ;;
    esac
done

source /opt/ros/humble/setup.bash
source "${base_ws}/install/setup.bash"
source "${agent_ws}/install/setup.bash"

test_client="${base_ws}/src/jqr_base/scripts/mcu_aux_test.py"
if [[ ! -f "${test_client}" ]]; then
    echo "Missing MCU test client: ${test_client}" >&2
    exit 2
fi

echo "[1/5] Required service discovery"
required_services=(
    /clear_fault
    /set_medicine_box_command
    /get_medicine_box_status
    /set_status_light_scene
    /get_status_light_state
)
service_list="$(ros2 service list)"
for service_name in "${required_services[@]}"; do
    if ! grep -qx "${service_name}" <<<"${service_list}"; then
        echo "MISSING ${service_name}" >&2
        exit 2
    fi
    echo "FOUND   ${service_name}"
done

echo "[2/5] SDK check and read-only status"
python3 "${test_client}" check
python3 "${test_client}" status

echo "[3/5] DAY status-light verification"
python3 "${test_client}" light working --ambient day --restart --verify
python3 "${test_client}" light waiting --ambient day --restart --verify

if [[ "${all_light_scenes}" == true ]]; then
    echo "[3b/5] All documented DAY scenes"
    for scene in off waiting working safety_alert fault estop low_battery critical_battery charging upgrading pairing; do
        echo "Testing DAY scene: ${scene}"
        python3 "${test_client}" light "${scene}" --ambient day --restart --verify
    done
    python3 "${test_client}" light waiting --ambient day --restart --verify
fi

echo "[4/5] Fault clear"
if [[ "${clear_fault}" == true ]]; then
    if [[ "${JQR_ALLOW_FAULT_CLEAR:-0}" != "1" ]]; then
        echo "Refusing fault clear: set JQR_ALLOW_FAULT_CLEAR=1 after confirming recovery conditions." >&2
        exit 2
    fi
    python3 "${test_client}" clear-fault --mask 0xffffffff
else
    echo "SKIPPED (use --clear-fault with JQR_ALLOW_FAULT_CLEAR=1)"
fi

echo "[5/5] Medicine-box mechanical actions"
if [[ "${mechanical}" == true ]]; then
    if [[ "${JQR_ALLOW_MECHANICAL_TEST:-0}" != "1" ]]; then
        echo "Refusing mechanical test: clear the area, verify E-stop, then set JQR_ALLOW_MECHANICAL_TEST=1." >&2
        exit 2
    fi
    python3 "${test_client}" medicine open --wait --timeout 12
    python3 "${test_client}" medicine close --wait --timeout 12
    python3 "${test_client}" medicine stop
else
    echo "SKIPPED (use --mechanical with JQR_ALLOW_MECHANICAL_TEST=1)"
fi

echo "PASS: Sunrise MCU auxiliary acceptance test completed."

