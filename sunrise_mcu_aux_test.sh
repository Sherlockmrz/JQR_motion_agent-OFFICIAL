#!/bin/bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
base_ws="${JQR_BASE_WS:-/app/jqr_ws}"
mechanical_test=false
clear_fault_test=false

for arg in "$@"; do
    case "${arg}" in
        --mechanical) mechanical_test=true ;;
        --clear-fault) clear_fault_test=true ;;
        *) echo "Unknown argument: ${arg}" >&2; exit 2 ;;
    esac
done

source /opt/ros/humble/setup.bash
source "${base_ws}/install/setup.bash"
source "${script_dir}/install/setup.bash"

test_client="${base_ws}/src/jqr_base/scripts/mcu_aux_test.py"
if [ ! -f "${test_client}" ]; then
    echo "Missing MCU test client: ${test_client}" >&2
    exit 2
fi

python3 "${test_client}" check
python3 "${test_client}" status
python3 "${test_client}" light working --ambient day --restart --verify
python3 "${test_client}" light waiting --ambient day --restart --verify

if [ "${clear_fault_test}" = true ]; then
    if [ "${JQR_ALLOW_FAULT_CLEAR:-0}" != "1" ]; then
        echo "Set JQR_ALLOW_FAULT_CLEAR=1 after checking physical recovery conditions." >&2
        exit 2
    fi
    python3 "${test_client}" clear-fault --mask 0xffffffff
fi

if [ "${mechanical_test}" = true ]; then
    if [ "${JQR_ALLOW_MECHANICAL_TEST:-0}" != "1" ]; then
        echo "Set JQR_ALLOW_MECHANICAL_TEST=1 after clearing the medicine-box area and checking E-stop." >&2
        exit 2
    fi
    python3 "${test_client}" medicine open --wait --timeout 12
    python3 "${test_client}" medicine close --wait --timeout 12
    python3 "${test_client}" medicine stop
fi

echo "Sunrise MCU auxiliary acceptance test passed."
