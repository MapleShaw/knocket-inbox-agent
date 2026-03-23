# Knocket Inbox Agent 使用说明书

> 让 AI 帮你自动回复 Knocket Inbox 的客户消息。后台运行，不打扰你用浏览器。

---

## 目录

1. [这是什么](#这是什么)
2. [三种模式怎么选](#三种模式怎么选)
3. [快速开始](#快速开始)
   - [前置准备](#前置准备)
   - [方案 A：企微全自动](#方案-a企微全自动)
   - [方案 B：Telegram 人工优先](#方案-btelegram-人工优先)
   - [方案 C：微信人工优先](#方案-c微信人工优先)
4. [日常使用](#日常使用)
5. [自定义 AI 回复风格](#自定义-ai-回复风格)
6. [常见问题排查](#常见问题排查)
7. [进阶配置](#进阶配置)
8. [已知限制](#已知限制)
9. [原理简述](#原理简述)

---

## 这是什么

Knocket Inbox Agent 是一个运行在本地的客服监控脚本。它通过 Chrome DevTools Protocol (CDP) **在后台**监控你的 Knocket Inbox 页面——不会弹窗、不会抢焦点、不会干扰你正常用浏览器。

它做的事情很简单：

1. 每 60 秒扫一遍你的 inbox，看看有没有客户发了新消息
2. 有新消息 → 根据你选的模式处理（AI 自动回复 or 通知你来决定）
3. 回复完毕 → 通知你处理结果

---

## 三种模式怎么选

> **重要：开始之前请先想好用哪种模式。** 选错了也没关系，随时可以停一个、启另一个。

**一句话总结：**
- **方案 A（企微）**：AI 先回复，再通知你回了什么。省心，但你无法事先审核。
- **方案 B（Telegram）**：先通知你，你有 5 分钟决定怎么回。你不回，AI 再兜底。
- **方案 C（微信）**：和方案 B 一样的人工优先模式，但通知走微信。⭐ 国内用户推荐。

| 我的场景 | 推荐模式 |
|---|---|
| 咨询量大，问题标准化，不需要逐条过目 | **方案 A**：企微全自动 |
| 客户重要，需要人工把关回复内容 | **方案 B** 或 **方案 C** |
| 国内用户，习惯用微信 | **方案 C**：微信人工优先 ⭐ |
| 需要翻墙才能用 Telegram | **方案 C**：微信人工优先 |
| 白天人工看，晚上自动回 | **方案 B/C**（设个长等待时间） |
| 先跑起来试试 | **方案 C**（微信最方便，可控性强） |
| 第一次用，不确定 | **方案 C** ⭐（推荐新手用这个） |

---

## 快速开始

### 前置准备

#### 1. 用远程调试模式启动 Chrome

先完全退出 Chrome（确保没有残留进程），然后：

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

验证：
```bash
curl -s http://127.0.0.1:9222/json/version
# 有输出就对了
```

#### 2. 打开 Knocket Inbox 并登录

在这个 Chrome 里打开 https://console.trtc.io/knocket-inbox ，确保已登录且能看到会话列表。

#### 3. 安装 Python 依赖

```bash
pip3 install websockets
```

#### 4. 准备 AI API（可选但推荐）

需要一个兼容 Anthropic 格式的 API 端点和密钥。如果不配，会使用固定兜底回复。

---

### 方案 A：企微全自动

**5 分钟搞定，之后全自动运行。**

```bash
# 1. 进入工作目录（日志和状态文件会存在这里）
mkdir -p ~/knocket-agent && cd ~/knocket-agent

# 2. 设置环境变量
export WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的KEY"
export ANTHROPIC_BASE_URL="https://你的API地址"
export ANTHROPIC_API_KEY="你的密钥"
export KNOCKET_WORK_DIR="$(pwd)"

# 3. 启动（⚠️ 必须用 > /dev/null）
nohup python3 /path/to/skill/scripts/wecom_auto.py > /dev/null 2>&1 &
echo "启动成功，PID: $!"

# 4. 看日志确认正常
tail -f inbox_monitor.log
```

搞定。现在有客户发消息，AI 会自动回复，企微群里会收到通知。

---

### 方案 B：Telegram 人工优先

**推荐模式。你可以在手机上审核每条回复。**

#### 第一步：创建 Telegram Bot（一次性操作，3 分钟）

1. 打开 Telegram，搜索 **@BotFather**
2. 发送 `/newbot`，按提示给 bot 取名
3. BotFather 会给你一串 Token，类似 `123456:ABC-DEF1234...`，**记下来**
4. 打开你的新 bot 对话，**随便发一条消息**（这一步必须做，否则拿不到 Chat ID）
5. 获取你的 Chat ID：
   ```bash
   curl -s "https://api.telegram.org/bot你的TOKEN/getUpdates" | python3 -m json.tool | grep '"id"'
   ```
   找到 `"chat": {"id": 数字}`，那个数字就是你的 Chat ID

6. 测试一下：
   ```bash
   curl -s "https://api.telegram.org/bot你的TOKEN/sendMessage" \
     -d chat_id=你的CHATID -d text="连接成功！"
   ```
   Telegram 收到消息就说明 OK。

#### 第二步：启动

```bash
# 1. 进入工作目录
mkdir -p ~/knocket-agent && cd ~/knocket-agent

# 2. 设置环境变量
export TG_BOT_TOKEN="你的BOT_TOKEN"
export TG_CHAT_ID="你的CHAT_ID"
export ANTHROPIC_BASE_URL="https://你的API地址"
export ANTHROPIC_API_KEY="你的密钥"
export KNOCKET_WORK_DIR="$(pwd)"

# 3. 启动
nohup python3 /path/to/skill/scripts/telegram_human.py > /dev/null 2>&1 &
echo "启动成功，PID: $!"

# 4. 看日志
tail -f inbox_monitor.log
```

启动后 Telegram 会收到 "🟢 Knocket 客服监控已启动！"。

#### 第三步：日常使用

有客户发消息时，你的 Telegram 会收到类似这样的通知：

```
📬 新客户消息

👤 客户: 张三
💬 新消息: 你好，请问你们的设计服务价格是多少？

📋 最近对话:
  👤客户: 你好
  💼客服: 您好！请问有什么可以帮您？
  👤客户: 你好，请问你们的设计服务价格是多少？

⏰ 你有 5 分钟回复我该怎么回。
直接打字告诉我回复内容即可，超时将 AI 自动回复。
```

你可以：
- **直接回复**：比如打 `Logo 设计 3000-8000 元，品牌全案另议。需要了解下您的具体需求` → 客户就会收到这段话
- **不回复**：5 分钟后 AI 自动回复，Telegram 会告诉你 AI 回了什么

---

### 方案 C：微信人工优先

**推荐模式。国内用户首选，直接在微信上操作。**

#### 第一步：安装 OpenClaw + 微信插件（一次性操作，5 分钟）

OpenClaw 是一个 Agent 框架，它的微信插件提供了 iLink Bot API，让脚本能通过微信收发消息。

```bash
# 1. 安装 OpenClaw CLI（需要 Node.js ≥ 16）
npm install -g openclaw

# 2. 安装微信插件
openclaw plugin install @tencent-weixin/openclaw-weixin

# 3. 启动微信网关（会弹出二维码）
openclaw run @tencent-weixin/openclaw-weixin
```

用微信扫码登录后，终端显示：
```
✅ WeChat iLink Bot started
Bot Token: accountId@im.bot:xxxxxxxx
Your User ID: wxid_xxxxxxxx
```

**记下 Bot Token 和 Your User ID**。

> **💡 提示**：OpenClaw 微信网关需要保持后台运行。建议用 `nohup openclaw run @tencent-weixin/openclaw-weixin > /dev/null 2>&1 &` 后台启动。

#### 第二步：启动

```bash
# 1. 进入工作目录
mkdir -p ~/knocket-agent && cd ~/knocket-agent

# 2. 设置环境变量
export WX_BOT_TOKEN="你的BOT_TOKEN"              # OpenClaw 启动时显示的 Bot Token
export WX_ADMIN_USER_ID="你的USER_ID"              # OpenClaw 启动时显示的 Your User ID
export ANTHROPIC_BASE_URL="https://你的API地址"
export ANTHROPIC_API_KEY="你的密钥"
export KNOCKET_WORK_DIR="$(pwd)"

# 3. 启动
nohup python3 /path/to/skill/scripts/wechat_human.py > /dev/null 2>&1 &
echo "启动成功，PID: $!"

# 4. 看日志
tail -f inbox_monitor.log
```

启动后微信会收到 "🟢 Knocket 客服监控已启动！"。

#### 第三步：日常使用

有客户发消息时，你的微信会收到类似这样的通知：

```
📬 新客户消息

👤 客户: 张三
💬 新消息: 你好，请问你们的设计服务价格是多少？

📋 最近对话:
  👤客户: 你好
  💼客服: 您好！请问有什么可以帮您？
  👤客户: 你好，请问你们的设计服务价格是多少？

⏰ 你有 5 分钟回复我该怎么回。
直接打字告诉我回复内容即可，超时将 AI 自动回复。
```

你可以：
- **直接回复**：比如打 `Logo 设计 3000-8000 元，品牌全案另议` → 客户就会收到这段话
- **不回复**：5 分钟后 AI 自动回复，微信会告诉你 AI 回了什么

---

## 日常使用

### 查看运行状态

```bash
# 进程是否在跑
ps aux | grep -E "wecom_auto|telegram_human|wechat_human" | grep -v grep

# 最新日志
tail -20 ~/knocket-agent/inbox_monitor.log
```

### 停止

```bash
pkill -f wechat_human   # 或 telegram_human 或 wecom_auto
```

### 重启

```bash
# 先停
pkill -f telegram_human

# 重新设置环境变量（如果新终端）
export TG_BOT_TOKEN="..." TG_CHAT_ID="..." ...
export KNOCKET_WORK_DIR=~/knocket-agent

# 再启
cd ~/knocket-agent
nohup python3 /path/to/skill/scripts/telegram_human.py > /dev/null 2>&1 &
```

### 容错机制（方案 B/C 共有）

你不需要额外操心这些，它们自动运行：

- **CDP 连接断了** → 自动重连
- **页面休眠** → 自动 reload 并等待加载完成
- **会话列表变了** → 用名字而非序号定位客户，处理完一个就重新扫描
- **发送失败** → 自动重试 3 次，每次完全重建连接
- **Send 按钮不可用** → 自动切换 Enter 键发送

---

## 自定义 AI 回复风格

在工作目录创建 `config.toml`，或运行 `setup.sh` 自动生成模板：

```bash
bash /path/to/skill/scripts/setup.sh ~/knocket-agent
```

然后编辑 `~/knocket-agent/config.toml`：

```toml
[custom_rules]
# 人设
persona = "你是一个热情专业的客服，代表 XX 设计工作室。"

# 业务背景
business_context = "主营品牌设计、UI/UX 设计，价格 5000-50000 元。"

# 回复规则
reply_rules = """
用中文回复，语气温暖专业
1-3 句话即可
不要用 emoji
报价说"具体价格需要根据需求评估"
"""

# 知识库
knowledge_base = """
Q: 设计周期多久？
A: Logo 3-5 个工作日，品牌全案 2-4 周。

Q: 可以修改几次？
A: 无限次修改直到满意。
"""
```

预览效果：
```bash
python3 /path/to/skill/scripts/parse_config.py ~/knocket-agent/config.toml system_prompt
```

> 详细的自定义指南见 `references/customization.md`。

---

## 常见问题排查

### "未找到 inbox 标签页"

Chrome 没有用远程调试模式启动，或 inbox 页面关了。

```bash
# 验证 CDP 端口
curl -s http://127.0.0.1:9222/json/version

# 验证 inbox 标签页
curl -s http://127.0.0.1:9222/json/list | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    if 'knocket-inbox' in t.get('url',''): print(t['url'][:80])
"
```

### "没有会话"

页面可能登录过期了。去 Chrome 里刷新 inbox 页面，重新登录。

### Telegram 收不到通知

```bash
# 测试 Bot 是否能发消息
curl -s "https://api.telegram.org/bot你的TOKEN/sendMessage" \
  -d chat_id=你的CHATID -d text=test
```

如果报错，检查 TOKEN 和 CHAT_ID 是否正确。

### 微信收不到通知

```bash
# 测试 iLink Bot 是否能发消息
curl -s -X POST "https://ilinkai.weixin.qq.com/ilink/bot/sendmessage" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的BOT_TOKEN" \
  -d '{"user_id":"你的USER_ID","msg_type":"text","content":{"text":"test"}}'
```

如果报错：
- 检查 OpenClaw 微信网关是否在运行（`ps aux | grep openclaw | grep -v grep`）
- 微信登录态可能过期，需要重新 `openclaw run @tencent-weixin/openclaw-weixin` 并扫码

### 进程启动后很快退出

```bash
# 查看错误信息
python3 /path/to/skill/scripts/telegram_human.py
# 直接前台运行，看报错
```

常见原因：`pip3 install websockets` 没装、环境变量没设。

### 日志每行重复两次

启动命令用了 `>> inbox_monitor.log` 而不是 `> /dev/null`。脚本内部自己写日志文件，stdout 不需要再追加到同一个文件。

---

## 进阶配置

### 环境变量一览

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CHECK_INTERVAL` | `60` | 检查间隔（秒） |
| `HUMAN_WAIT_SECONDS` | `300` | 等人工回复超时（秒，方案B/C） |
| `CDP_PORT` | `9222` | Chrome 远程调试端口 |
| `KNOCKET_WORK_DIR` | 脚本所在目录 | 工作目录（日志/状态文件存放地） |
| `TG_BOT_TOKEN` | | Telegram Bot Token（方案B必填） |
| `TG_CHAT_ID` | | Telegram Chat ID（方案B必填） |
| `WX_BOT_TOKEN` | | 微信 iLink Bot Token（方案C必填） |
| `WX_ADMIN_USER_ID` | | 微信管理员 User ID（方案C必填） |
| `WX_BASE_URL` | `https://ilinkai.weixin.qq.com` | iLink API 地址（方案C，一般不改） |
| `WECOM_WEBHOOK` | | 企业微信 Webhook URL（方案A必填，B/C可选） |
| `ANTHROPIC_BASE_URL` | | AI API 地址 |
| `ANTHROPIC_API_KEY` | | AI API 密钥 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | AI 模型名 |

### 用 systemd / launchd 做守护进程

如果你希望脚本开机自启、崩溃自动重启，可以配置系统服务。

**macOS (launchd)**：

创建 `~/Library/LaunchAgents/com.knocket.inbox-agent.plist`：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.knocket.inbox-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/telegram_human.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TG_BOT_TOKEN</key>
        <string>你的TOKEN</string>
        <key>TG_CHAT_ID</key>
        <string>你的CHATID</string>
        <key>KNOCKET_WORK_DIR</key>
        <string>/Users/你/knocket-agent</string>
        <!-- 其他环境变量... -->
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>/Users/你/knocket-agent/error.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.knocket.inbox-agent.plist
```

---

## 已知限制

这些是客观存在的限制，代码已做最大程度缓解，但无法完全消除：

1. **Chrome 必须带 `--remote-debugging-port=9222` 启动** — Chrome 更新或系统重启后可能需要重新用调试端口启动
2. **Knocket Inbox 登录态会过期** — 脚本不能自动登录，需要你手动刷新页面重新登录
3. **macOS 睡眠后 SPA 状态可能丢失** — 代码会自动 reload 页面，但如果登录态也没了，仍需手动干预
4. **同名会话无法区分** — 如果两个客户显示名完全相同可能误发（实际极罕见）
5. **Send 按钮可能 disabled** — 代码会自动 fallback 到 Enter 键发送，实测可靠
6. **微信登录态会过期（方案C）** — OpenClaw 微信网关的登录态不是永久的，过期后需要重新扫码登录

> 详细说明见 SKILL.md 中的"已知限制"章节。

---

## 原理简述

```
你的 Chrome (端口 9222)
    │
    └── Knocket Inbox 标签页
         │
         │ CDP WebSocket（后台直连，不影响你操作浏览器）
         │
    ┌────┴─────────────────────────────────────────────┐
    │ wechat_human.py / telegram_human.py /            │
    │ wecom_auto.py                                    │
    │                                                  │
    │  每 60 秒：                                       │
    │  1. WebSocket 连接到 inbox 标签页                 │
    │  2. 执行 JS 获取会话列表和消息                     │
    │  3. 比对状态文件，发现新消息                        │
    │  4. 通知你 → 等你回复 → AI 兜底                   │
    │  5. 通过 CDP 在后台填入文字并点击发送               │
    └──────────────────────────────────────────────────┘
         │          │              │              │
    微信 iLink  Telegram Bot  企业微信 Webhook  Anthropic API
    Bot (方案C)  (方案B)       (方案A)           (AI 回复)
```

核心特点：
- **纯 CDP WebSocket 后台操作**——不弹窗、不抢焦点、不影响你用浏览器
- **消息签名去重**——同一条消息不会重复处理
- **Human-in-the-loop**——重要消息人工把关，不重要的 AI 兜底
- **三种通知渠道**——微信、Telegram、企业微信，选适合你的
- **多层容错**——自动重连、页面 reload、会话名精确匹配、3 次重试
