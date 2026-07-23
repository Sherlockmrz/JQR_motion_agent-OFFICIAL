# Sunrise MCU auxiliary deployment bundle

This directory keeps the Sunrise deployment and acceptance material together.
Nothing is copied directly into `/home/sunrise`.

Default remote layout:

```text
/home/sunrise/jqr_deploy/JQR_motion_agent_20260719/
├── agent/          # Motion Agent source and its colcon build
├── base_ws/        # jqr_base workspace from the supplied SDK archive
├── sdk_source/     # extracted, unchanged SDK delivery tree
├── tools/          # install/test scripts and expected results
└── logs/
```

From Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\sunrise_mcu_aux_20260719\deploy_to_sunrise.ps1
```

The default command creates the remote folder and uploads one agent archive plus
the tools directory. It does not overwrite `/app/jqr_ws` and does not start the
robot. To upload and then build both workspaces:

```powershell
.\deploy\sunrise_mcu_aux_20260719\deploy_to_sunrise.ps1 -Install
```

If password authentication is used, omit `-BatchMode` so `ssh`/`scp` can ask for
the `sunrise` password. With SSH key authentication, use `-BatchMode` for a
non-interactive deployment.

After installation, follow `EXPECTED_RESULTS.md` in the remote `tools` folder.

