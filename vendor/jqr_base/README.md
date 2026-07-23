# JQR Base MCU SDK bundle

`jqr_base_usb_base_20260716_185607.tar.gz` is the unchanged Sunrise aarch64
base workspace supplied for the MCU new SDK.

- SHA256: `AEE8BACA5F0CD5A8448411FDC429743DEF8AA506CB9D1AC05B7FA866C9D5B1BB`
- Target: Ubuntu 22.04, ROS 2 Humble, Sunrise X3/X5 aarch64
- Runtime workspace: `/app/jqr_ws`

Keep the archive compressed in this repository. Do not extract its nested
`jqr_ws/src/jqr_common/jqr_ros_msgs` under the Agent workspace: this repository
already contains a superset package with the same ROS package name, and colcon
rejects duplicate package names.

See `SUNRISE_MCU_AUX_DEPLOY.md` in the repository root for deployment and
hardware acceptance tests.
