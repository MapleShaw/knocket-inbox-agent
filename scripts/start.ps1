# start.ps1 - Windows 启动脚本
# 用法：在仓库根目录执行 .\scripts\start.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ScriptDir ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Host "❌ 找不到 .env 文件，请先复制模板：" -ForegroundColor Red
    Write-Host "   cp scripts\.env.example scripts\.env" -ForegroundColor Yellow
    Write-Host "   然后填入你的 API Key 等配置" -ForegroundColor Yellow
    exit 1
}

# 读取 .env 并设置环境变量
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match '^([^=]+)=(.*)$') {
        $key = $Matches[1].Trim()
        $val = $Matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
    }
}

# 自动设置 KNOCKET_WORK_DIR（若未配置）
if (-not $env:KNOCKET_WORK_DIR) {
    $env:KNOCKET_WORK_DIR = $ScriptDir
}

Write-Host "🚀 启动 Knocket 客服监控..." -ForegroundColor Green
Write-Host "   CHECK_INTERVAL     = $env:CHECK_INTERVAL s" -ForegroundColor Cyan
Write-Host "   HUMAN_WAIT_SECONDS = $env:HUMAN_WAIT_SECONDS s" -ForegroundColor Cyan
Write-Host "   AI_MODEL           = $env:AI_MODEL" -ForegroundColor Cyan
Write-Host ""

python3 "$ScriptDir\knocket_monitor.py"
