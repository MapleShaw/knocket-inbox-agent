#!/bin/bash
# start.sh - macOS / Linux 启动脚本
# 用法：在仓库根目录执行 bash scripts/start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 找不到 .env 文件，请先复制模板："
    echo "   cp scripts/.env.example scripts/.env"
    echo "   然后填入你的 API Key 等配置"
    exit 1
fi

# 读取 .env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# 自动设置 KNOCKET_WORK_DIR（若未配置）
export KNOCKET_WORK_DIR="${KNOCKET_WORK_DIR:-$SCRIPT_DIR}"

echo "🚀 启动 Knocket 客服监控..."
echo "   CHECK_INTERVAL     = ${CHECK_INTERVAL:-60} s"
echo "   HUMAN_WAIT_SECONDS = ${HUMAN_WAIT_SECONDS:-300} s"
echo "   AI_MODEL           = ${AI_MODEL}"
echo ""

python3 "$SCRIPT_DIR/knocket_monitor.py"
