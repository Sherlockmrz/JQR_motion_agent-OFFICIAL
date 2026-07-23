param(
    [string]$Robot = "sunrise@192.168.31.75",
    [string]$RemoteRoot = "/home/sunrise/jqr_deploy/JQR_motion_agent_20260719",
    [switch]$Install,
    [switch]$BatchMode
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stageRoot = Join-Path $env:TEMP "jqr_sunrise_deploy_$stamp"
$bundlePath = Join-Path $stageRoot "agent_bundle.tar.gz"

New-Item -ItemType Directory -Path $stageRoot | Out-Null

try {
    $required = @(
        "smart_robot_agent.py",
        "jqr_ros_msgs\srv\ClearFault.srv",
        "jqr_ros_msgs\srv\MedicineBoxCommand.srv",
        "jqr_ros_msgs\srv\MedicineBoxStatus.srv",
        "jqr_ros_msgs\srv\StatusLightScene.srv",
        "jqr_ros_msgs\srv\StatusLightState.srv",
        "vendor\jqr_base\jqr_base_usb_base_20260716_185607.tar.gz"
    )
    foreach ($relativePath in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $relativePath))) {
            throw "Missing required deployment file: $relativePath"
        }
    }

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (
        Join-Path $repoRoot "vendor\jqr_base\jqr_base_usb_base_20260716_185607.tar.gz"
    )).Hash
    $expectedHash = "AEE8BACA5F0CD5A8448411FDC429743DEF8AA506CB9D1AC05B7FA866C9D5B1BB"
    if ($hash -ne $expectedHash) {
        throw "SDK archive SHA256 mismatch. Expected $expectedHash, got $hash"
    }

    Push-Location $repoRoot
    try {
        & tar -czf $bundlePath `
            --exclude=.git `
            --exclude=.env `
            --exclude=__pycache__ `
            --exclude=build `
            --exclude=install `
            --exclude=log `
            --exclude=logs `
            --exclude=videos `
            --exclude=_local_docs_archive_do_not_upload `
            --exclude=history.db `
            --exclude=Jrobot_agent_base.tar `
            --exclude='*.patch' `
            --exclude=deploy `
            .
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the agent deployment archive"
        }
    }
    finally {
        Pop-Location
    }

    $sshOptions = @("-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new")
    if ($BatchMode) {
        $sshOptions += @("-o", "BatchMode=yes")
    }

    & ssh @sshOptions $Robot "mkdir -p '$RemoteRoot/tools' '$RemoteRoot/logs'"
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot create the remote deployment directory"
    }

    & scp @sshOptions $bundlePath "${Robot}:${RemoteRoot}/agent_bundle.tar.gz"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload agent_bundle.tar.gz"
    }

    $toolFiles = @(
        "remote_install.sh",
        "run_hardware_tests.sh",
        "EXPECTED_RESULTS.md"
    )
    foreach ($toolFile in $toolFiles) {
        & scp @sshOptions (Join-Path $scriptDir $toolFile) "${Robot}:${RemoteRoot}/tools/$toolFile"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to upload $toolFile"
        }
    }

    & ssh @sshOptions $Robot "chmod +x '$RemoteRoot/tools/remote_install.sh' '$RemoteRoot/tools/run_hardware_tests.sh' && sha256sum '$RemoteRoot/agent_bundle.tar.gz'"
    if ($LASTEXITCODE -ne 0) {
        throw "Upload completed, but remote verification failed"
    }

    if ($Install) {
        & ssh @sshOptions $Robot "'$RemoteRoot/tools/remote_install.sh' '$RemoteRoot'"
        if ($LASTEXITCODE -ne 0) {
            throw "Remote build/install failed"
        }
    }

    Write-Host "Deployment uploaded to ${Robot}:${RemoteRoot}"
    Write-Host "Remote tests: cd '$RemoteRoot' && ./tools/run_hardware_tests.sh"
}
finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}

