param(
    [string]$RobotHost = "192.168.31.75",
    [string]$RobotUser = "sunrise",
    [string]$RemoteLogDir = "/home/sunrise/jqr_deploy/JQR_20260722/agent/logs/agent",
    [int]$Limit
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$snapshotDir = Join-Path $PSScriptRoot "agent_log_snapshots\$timestamp"
$reportDir = Join-Path $PSScriptRoot "agent_score_reports"
New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null

$remoteSpec = "${RobotUser}@${RobotHost}:${RemoteLogDir}/agent_*.log"
Write-Host "正在从机器人抓取 Agent 日志快照..."
& scp $remoteSpec $snapshotDir
if ($LASTEXITCODE -ne 0) {
    throw "scp 获取日志失败，退出码 $LASTEXITCODE"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "没有找到 python 或 python3"
}

$scoreArgs = @(
    (Join-Path $PSScriptRoot "agent_trace_scorer.py"),
    "--log-dir", $snapshotDir,
    "--output-dir", $reportDir
)
if ($PSBoundParameters.ContainsKey("Limit")) {
    $scoreArgs += @("--limit", $Limit)
}

& $python.Source @scoreArgs

if ($LASTEXITCODE -ne 0) {
    throw "Trace 评分失败，退出码 $LASTEXITCODE"
}
