#!/usr/bin/env bash

set -euo pipefail

remote_root="${1:-/home/sunrise/jqr_deploy/JQR_motion_agent_20260719}"
bundle="${remote_root}/agent_bundle.tar.gz"
agent_dir="${remote_root}/agent"
sdk_source="${remote_root}/sdk_source"
base_ws="${remote_root}/base_ws"
expected_sdk_sha="aee8baca5f0cd5a8448411fdc429743def8aa506cb9d1ac05b7fa866c9d5b1bb"

if [[ ! -f "${bundle}" ]]; then
    echo "Missing deployment archive: ${bundle}" >&2
    exit 2
fi

mkdir -p "${agent_dir}" "${sdk_source}" "${remote_root}/logs"
tar -xzf "${bundle}" -C "${agent_dir}"

sdk_archive="${agent_dir}/vendor/jqr_base/jqr_base_usb_base_20260716_185607.tar.gz"
if [[ ! -f "${sdk_archive}" ]]; then
    echo "Missing MCU SDK archive in agent bundle" >&2
    exit 2
fi

actual_sdk_sha="$(sha256sum "${sdk_archive}" | awk '{print $1}')"
if [[ "${actual_sdk_sha}" != "${expected_sdk_sha}" ]]; then
    echo "MCU SDK SHA256 mismatch: ${actual_sdk_sha}" >&2
    exit 2
fi

if [[ ! -f "${base_ws}/src/jqr_base/package.xml" ]]; then
    tar -xzf "${sdk_archive}" -C "${sdk_source}"
    delivered_ws="${sdk_source}/jqr_base_usb_base_20260716_185607/jqr_base/jqr_ws"
    if [[ ! -d "${delivered_ws}" ]]; then
        echo "The supplied archive does not contain the expected jqr_ws" >&2
        exit 2
    fi
    cp -a "${delivered_ws}" "${base_ws}"
fi

source /opt/ros/humble/setup.bash

cd "${base_ws}"
colcon build --symlink-install

source "${base_ws}/install/setup.bash"
cd "${agent_dir}"
colcon build --symlink-install

chmod +x "${agent_dir}/start_agent.sh" \
    "${remote_root}/tools/run_hardware_tests.sh"

echo "Install complete."
echo "Base workspace: ${base_ws}"
echo "Agent workspace: ${agent_dir}"
echo "No service or mechanical command has been started automatically."

