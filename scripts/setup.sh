#!/bin/bash
# ============================================
# Knocket Inbox Agent - 一键初始化
# 在工作目录创建配置文件并验证前置条件
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR="${1:-$(pwd)}"

echo "🚀 Knocket Inbox Agent 初始化"
echo "================================"
echo "工作目录: $WORK_DIR"
echo ""

# 创建工作目录
mkdir -p "$WORK_DIR"

# 复制配置模板
CONFIG_FILE="${WORK_DIR}/config.toml"
if [ -f "$CONFIG_FILE" ]; then
    echo "⚠️  config.toml 已存在，跳过创建（已有配置不会被覆盖）"
else
    cp "${SKILL_DIR}/assets/config.template.toml" "$CONFIG_FILE"
    echo "✅ 已创建 config.toml 配置文件"
fi

# 初始化状态文件
STATE_FILE="${WORK_DIR}/.inbox_state.json"
[ ! -f "$STATE_FILE" ] && echo '{}' > "$STATE_FILE"

# 检查前置条件
echo ""
echo "🔍 检查前置条件..."
echo ""

# 1. Chrome 远程调试
CHROME_PORT=9222
if curl -s "http://127.0.0.1:${CHROME_PORT}/json/version" >/dev/null 2>&1; then
    echo "✅ Chrome 远程调试 (端口 ${CHROME_PORT}) — 已就绪"
else
    echo "❌ Chrome 远程调试 (端口 ${CHROME_PORT}) — 未检测到"
    echo "   请用以下命令重启 Chrome："
    echo "   /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=${CHROME_PORT}"
fi

# 2. Python websockets
if python3 -c "import websockets" 2>/dev/null; then
    echo "✅ websockets 库 — 已安装"
else
    echo "❌ websockets 库 — 未安装"
    echo "   运行: pip3 install websockets"
fi

# 3. Inbox 页面
INBOX_FOUND=$(curl -s "http://127.0.0.1:${CHROME_PORT}/json/list" 2>/dev/null | python3 -c "
import json, sys
try:
    tabs = json.load(sys.stdin)
    count = sum(1 for t in tabs if 'knocket-inbox' in t.get('url', '') and t.get('type') == 'page')
    print(count)
except:
    print(0)
" 2>/dev/null || echo "0")

if [ "$INBOX_FOUND" != "0" ]; then
    echo "✅ Knocket Inbox 页面 — 已打开 (${INBOX_FOUND} 个标签页)"
else
    echo "❌ Knocket Inbox 页面 — 未找到"
    echo "   请在 Chrome 中打开并登录: https://console.trtc.io/knocket-inbox"
fi

# 4. Python3
if command -v python3 >/dev/null 2>&1; then
    echo "✅ Python 3 — $(python3 --version 2>&1)"
else
    echo "❌ Python 3 — 未安装"
fi

echo ""
echo "================================"
echo "📝 下一步："
echo "1. 编辑 ${CONFIG_FILE} 填写你的配置"
echo "2. 确保上面所有前置条件为 ✅"
echo "3. 启动监控（二选一）："
echo "   方案A（全自动）: export KNOCKET_WORK_DIR=$(pwd) && nohup python3 ${SKILL_DIR}/scripts/wecom_auto.py > /dev/null 2>&1 &"
echo "   方案B（人工优先）: export KNOCKET_WORK_DIR=$(pwd) && nohup python3 ${SKILL_DIR}/scripts/telegram_human.py > /dev/null 2>&1 &"
echo ""
