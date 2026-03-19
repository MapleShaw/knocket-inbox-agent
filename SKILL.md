---
name: knocket-inbox-agent
description: "This skill should be used when the user wants to set up automated customer service monitoring for Knocket Inbox (console.trtc.io/knocket-inbox). It handles real-time chat monitoring, AI-powered smart replies, Telegram Bot notifications with human-in-the-loop control, and optional WeChat Work push notifications. Trigger phrases include knocket, inbox monitoring, auto reply to customers, 客服自动回复, knocket 监控, inbox agent, telegram 客服, or when the user mentions monitoring a Knocket chat inbox."
---

# Knocket Inbox Agent

Automated customer service agent for [Knocket Inbox](https://console.trtc.io/knocket-inbox).

> 💡 **这个 skill 能帮你做什么？** 你的 Knocket Inbox 收到客户消息后，AI 自动帮你回复，你在手机上就能收到通知、审核回复。不需要一直盯着电脑。

---

## ⚡ 第一步：选择你的模式

**在开始之前，请先选一种适合你的模式：**

### 🅰 方案 A：全自动（企业微信通知）

```
客户发消息 → AI 立即自动回复 → 企微群通知你"AI 刚才回了什么"
```

**适合**：咨询量大、问题标准化、不需要逐条审核的场景
**你需要**：企业微信群 Webhook

### 🅱 方案 B：人工优先（Telegram 通知）⭐ 推荐

```
客户发消息 → Telegram 通知你 → 你在手机上回复要说什么 → 脚本帮你发
              ↓ 5 分钟没回复
              AI 自动兜底回复 → Telegram 告诉你 AI 回了什么
```

**适合**：重要客户、需要人工把关、想要 Human-in-the-loop 的场景
**你需要**：Telegram Bot（下面会教你怎么创建，3 分钟搞定）

### 两种模式对比

| | **方案 A：企微全自动** | **方案 B：Telegram 人工优先** ⭐ |
|---|---|---|
| 脚本 | `wecom_auto.py` | `telegram_human.py` |
| AI 怎么介入 | **先 AI 回，再通知你** | **先通知你，你不回再 AI 兜底** |
| 通知渠道 | 企业微信群 Webhook | Telegram Bot 私聊 |
| 你需要操作吗 | 不需要，全自动 | 可选：5 分钟内在 Telegram 回复 |
| 适合场景 | 量大、标准化咨询 | 重要客户、需要人工把关 |
| 浏览器干扰 | ❌ 不干扰（纯 CDP 后台） | ❌ 不干扰（纯 CDP 后台） |
| 容错能力 | 基础 | 强（自动重连、页面 reload、3 次重试） |

> **选好了？** 往下看你选的方案对应的配置步骤。两个方案的前置准备是一样的。

---

## Prerequisites（两个方案通用）

| Requirement | How to Check | How to Fix |
|---|---|---|
| Chrome with remote debugging on port 9222 | `curl -s http://127.0.0.1:9222/json/version` | Restart Chrome: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222` |
| Knocket Inbox page open and logged in | Check Chrome tabs for `knocket-inbox` URL | Open `https://console.trtc.io/knocket-inbox` in Chrome and log in |
| Python 3 + `websockets` library | `python3 -c "import websockets"` | `pip3 install websockets` |

**方案 A 额外需要**：企业微信群 Webhook URL
**方案 B 额外需要**：Telegram Bot Token + Chat ID

---

## 方案 A：企微自动回复（`wecom_auto.py`）

### 流程

```
客户发消息
  → 脚本通过 CDP WebSocket 后台检测到（不影响浏览器）
  → AI 立即生成回复
  → 通过 CDP 后台发送回复
  → 企业微信群通知你：客户说了什么、AI 怎么回的
```

### 配置与启动

```bash
cd <working_directory>

# 必填：企业微信 Webhook
export WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"

# 必填：AI API（如果需要智能回复）
export AI_PROVIDER="anthropic"              # 或 "openai"（兼容 DeepSeek/通义千问/智谱等）
export AI_BASE_URL="https://your-api-endpoint"
export AI_API_KEY="your-api-key"

# 可选
export CHECK_INTERVAL="60"          # 检查间隔秒数，默认 60
export CDP_PORT="9222"              # Chrome 调试端口，默认 9222
export AI_MODEL="claude-haiku-4-5-20251001"  # 模型名
export AI_CUSTOM_HEADERS=""         # 自定义请求头（JSON 格式，可选）

# 启动
export KNOCKET_WORK_DIR="$(pwd)"
nohup python3 <skill_dir>/scripts/wecom_auto.py > /dev/null 2>&1 &
echo "PID: $!"
```

### 验证

```bash
tail -20 <working_directory>/inbox_monitor.log
```

应该看到：
```
🚀 ====== 客服监控启动 (v2 - 纯CDP后台模式) ======
💡 本版本使用纯 CDP 协议，不会占用你的浏览器窗口
🔍 开始检查 inbox...
📬 发现 N 个会话
```

---

## 方案 B：Telegram 人工优先（`telegram_human.py`）

### 流程

```
客户发消息
  → 脚本通过 CDP WebSocket 后台检测到（不影响浏览器）
  → Telegram Bot 通知你：客户说了什么 + 最近对话上下文
  → 等你回复（默认 5 分钟）
    → 你在 Telegram 回复 "告诉他明天发货"
      → 脚本按你说的回复客户
      → Telegram 确认 "✅ 已回复"
    → 5 分钟没回复
      → AI 自动生成回复
      → Telegram 通知你 "🤖 已自动回复：xxx"
```

### 第一步：创建 Telegram Bot

1. 在 Telegram 搜索 **@BotFather**，发送 `/newbot`
2. 按提示取名，获得 **Bot Token**
3. 在 Telegram 打开你的新 bot，发送一条消息（随便什么）
4. 获取你的 Chat ID：
   ```bash
   curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | python3 -m json.tool
   ```
   找到 `"chat": {"id": 数字}` — 这个数字就是你的 Chat ID
5. 测试发消息：
   ```bash
   curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/sendMessage" \
     -d chat_id=<YOUR_CHAT_ID> -d text="Bot 连接成功！"
   ```

### 第二步：配置与启动

```bash
cd <working_directory>

# 必填：Telegram
export TG_BOT_TOKEN="your-bot-token-from-botfather"
export TG_CHAT_ID="your-chat-id"

# 必填：AI API（超时回复用）
export AI_PROVIDER="anthropic"              # 或 "openai"
export AI_BASE_URL="https://your-api-endpoint"
export AI_API_KEY="your-api-key"

# 可选
export CHECK_INTERVAL="60"          # 检查间隔秒数，默认 60
export HUMAN_WAIT_SECONDS="300"     # 等人工回复秒数，默认 300（5分钟）
export CDP_PORT="9222"              # Chrome 调试端口，默认 9222
export WECOM_WEBHOOK=""             # 企微 Webhook（可选，额外通知渠道）
export AI_CUSTOM_HEADERS=""         # 自定义请求头（JSON 格式，可选）

# 启动（⚠️ 必须用 > /dev/null，因为脚本内部自己写日志文件）
export KNOCKET_WORK_DIR="$(pwd)"
nohup python3 <skill_dir>/scripts/telegram_human.py > /dev/null 2>&1 &
echo "PID: $!"
```

### 验证

```bash
tail -20 <working_directory>/inbox_monitor.log
```

应该看到：
```
🚀 ====== 客服监控启动 (方案B - Telegram 人工优先模式 telegram_human) ======
💡 流程: 新消息 → Telegram 通知你 → 等你回复 → 超时自动 AI 回复
🔍 开始检查 inbox...
```

同时你的 Telegram 应该收到一条 "🟢 Knocket 客服监控已启动！" 的消息。

### Telegram 操作指南

收到通知后，你可以：
- **直接打字回复**：你打什么，脚本就原样发给客户。比如你回复"3天内发货"，客户就会看到"3天内发货"
- **不理它**：5 分钟后 AI 自动回复，并把回复内容告诉你
- **随时查看**：Telegram 会记录每次通知和回复结果

---

## 通用操作

### 验证 Chrome 连接

```bash
# 检查 CDP 端口
curl -s http://127.0.0.1:9222/json/version

# 列出 inbox 标签页
curl -s http://127.0.0.1:9222/json/list | python3 -c "
import json, sys
tabs = json.load(sys.stdin)
for t in tabs:
    if 'knocket-inbox' in t.get('url', '') and t.get('type') == 'page':
        print(f\"Tab: {t['id'][:12]}  URL: {t['url'][:80]}\")
"

# 验证会话数（纯 CDP，不用 agent-browser）
python3 -c "
import json, urllib.request, asyncio, websockets
tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json/list').read())
inbox = [t for t in tabs if 'knocket-inbox' in t.get('url','') and t['type']=='page']
async def check():
    for t in inbox:
        async with websockets.connect(t['webSocketDebuggerUrl']) as ws:
            await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':'document.querySelectorAll(\".trtc-chat-session\").length','returnByValue':True}}))
            r = json.loads(await ws.recv())
            c = r.get('result',{}).get('result',{}).get('value',0)
            if c: print(f'Tab {t[\"id\"][:12]}: {c} sessions')
asyncio.run(check())
"
```

### 停止监控

```bash
# 方案 A
ps aux | grep wecom_auto | grep -v grep
kill <PID>

# 方案 B
ps aux | grep telegram_human | grep -v grep
kill <PID>
```

### 初始化（可选，用 setup.sh）

```bash
bash <skill_dir>/scripts/setup.sh <working_directory>
```

创建 `config.toml` 配置文件。配置也可以通过环境变量设置（环境变量优先级高于配置文件）。

---

## 技术架构

```
用户的浏览器 (Chrome:9222)
    │
    ├── Knocket Inbox 标签页 ← CDP WebSocket 直连（后台操作，不干扰前台）
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  telegram_human.py (方案B) / wecom_auto.py (方案A)  │
│                                                      │
│  CDPConnection 类：                                   │
│    ├── find_inbox_tab()   → HTTP 查找标签页           │
│    ├── connect()          → WebSocket 连接            │
│    ├── eval_js()          → Runtime.evaluate 执行 JS  │
│    ├── cdp_dom_focus()    → DOM.focus 聚焦元素        │
│    ├── dispatch_input_event() → Input.insertText 填值 │
│    ├── ensure_connected() → 自动重连 + reload         │
│    └── ensure_page_alive()→ 检测 SPA 休眠后 reload    │
│                                                      │
│  while True:                                         │
│    1. find_inbox_tab() via CDP HTTP                   │
│    2. connect() via WebSocket                         │
│    3. eval_js() 获取会话列表 + 消息                    │
│    4. 消息签名去重 (.inbox_state.json)                 │
│    5. 新客户消息:                                      │
│       - v2: AI 直接回复 → 企微通知                     │
│       - v3: TG通知 → 等人工 → AI兜底                  │
│    6. sleep(CHECK_INTERVAL)                           │
└──────────────────────────────────────────────────────┘
    │                    │                    │
    ▼                    ▼                    ▼
 Telegram Bot       企业微信 Webhook     Anthropic API
 (v3 主通道)        (v2 主 / v3 可选)    (AI 回复生成)
```

### CDP 操作链路（发送回复）

```
1. 完全重建 CDP 连接（关闭旧连接 → 重新查找 tab → 重新 WebSocket 连接）
2. find_session_by_name() 精确匹配会话名
3. eval_js click 点击会话
4. 等待 chatPanel + textarea 出现
5. DOM.getDocument → DOM.querySelector → DOM.focus（CDP 底层聚焦，绕过 JS 安全沙箱）
6. Input.insertText 写入文字（不依赖 .value 验证，React 控制组件读不出来）
7. 检查 Send 按钮状态 → 点击 Send 或 Enter 键发送
8. 验证 textarea 是否被清空
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "没有会话" in log | Inbox 页面没加载或登录过期 | 刷新 inbox 页面，必要时重新登录 |
| "未找到 inbox 标签页" | Chrome 标签页关了 | 确保 inbox 在 Chrome 中打开，检查 `curl http://127.0.0.1:9222/json/list` |
| AI 回复是兜底文案 | API 配置缺失或无效 | 检查 `AI_BASE_URL` 和 `AI_API_KEY` 环境变量，确认 `AI_PROVIDER` 设置正确 |
| 没收到企微通知（方案A） | Webhook 没配 | 设置 `WECOM_WEBHOOK` 环境变量 |
| 没收到 Telegram 通知（方案B） | Token 或 Chat ID 错误 | 用 `curl` 测试 Bot API 发消息 |
| Telegram 回复没被检测到（方案B） | 超时太短 / 网络问题 | 加大 `HUMAN_WAIT_SECONDS`，检查网络 |
| 脚本启动就退出 | Python 依赖缺失 | `pip3 install websockets` |
| 日志每行重复两次 | 启动命令用了 `>> log` 而非 `> /dev/null` | 改用 `nohup python3 xxx.py > /dev/null 2>&1 &`（脚本内部自己写日志） |
| focus 成功但 textarea.value 读不出来 | React 控制组件的 value 属性不同步 | 这是正常的，已在代码中处理——insertText 成功即视为成功 |
| Send 按钮一直 disabled | insertText 后 React 内部状态没更新 | 代码会自动用 Enter 键作为备选发送方式 |
| 回复发送了但文字重复 | dispatch_input_event 多次重试时累积写入 | 已修复——只用一种方案（DOM.focus + insertText），不再 fallback 多种方案 |
| 浏览器被干扰 | 跑的是旧版 v1 shell 脚本 | 确保运行的是 `wecom_auto.py` 或 `telegram_human.py` |

---

## 踩坑记录（CDP 后台操作 React 页面）

这些经验对任何需要用 CDP 后台操作 React SPA 的项目都有参考价值：

### 1. 后台 tab 的 focus 限制

**问题**：Chrome 对后台标签页有严格的安全限制。JS 的 `el.focus()` 即使加了 `userGesture: true` 也可能静默失败——activeElement 始终停在 `BODY`。

**解法**：用 CDP 协议级别的 `DOM.focus` 命令。流程：
```
DOM.getDocument(depth:0) → 拿到 root nodeId
DOM.querySelector(nodeId, selector) → 拿到目标 nodeId
DOM.focus(nodeId) → 底层聚焦，不受 JS 安全沙箱限制
```

### 2. React 控制组件的 value 读不出来

**问题**：通过 `Input.insertText` 写入 textarea 的文字，用 `el.value` 读出来是空的。React 通过 `_valueTracker` 等内部机制管理 value，CDP 的 `Input.insertText` 绕过了 React 的 onChange 路径。

**解法**：不依赖 `.value` 验证。`DOM.focus` 成功 + `Input.insertText` 没报 CDP error = 视为成功。最终验证放在 Send 按钮状态检查上。

### 3. React nativeSetter 在后台 tab 不可靠

**问题**：`Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set` + `dispatchEvent(new Event('input'))` 是常见的 React 注入方案，但在后台 tab 执行时经常返回 `undefined`。

**解法**：放弃 nativeSetter 方案，统一用 `DOM.focus` + `Input.insertText`。

### 4. 多方案 fallback 导致重复输入

**问题**：insertText 其实成功了（文字出现了），但 `.value` 读不出来 → 代码以为失败 → 继续执行方案 2/3/4 → 每个又写了一遍 → 文字重复了 2-4 遍。

**解法**：只用一种方案。不要在"验证失败"时 fallback 到其他写入方案——因为写入可能已经成功了，只是你读不出来。

### 5. Send 按钮 disabled

**问题**：`Input.insertText` 写入后，React 的状态管理可能没感知到变化，Send 按钮仍然是 disabled。

**解法**：用 Enter 键作为备选发送方式（`Input.dispatchKeyEvent` type=keyDown, key=Enter）。DOM.focus textarea 后直接发 Enter 即可。

### 6. 页面休眠后 SPA 状态丢失

**问题**：macOS 睡眠或长时间不操作后，Knocket Inbox 的 React SPA 可能丢失会话状态——CDP 能连上 tab 但查不到 `.trtc-chat-session` 元素。

**解法**：检测到 sessions=0 时自动 `Page.reload`，等待最多 20 秒让页面重新加载。

### 7. 会话 index 过时

**问题**：check_inbox 获取会话列表的快照后，在处理某个会话的过程中（发 Telegram 通知 → 等 5 分钟 → 发送回复），其他会话可能新增/删除，导致 index 不再对应原来的客户。

**解法**：用 session_name 而非 index 定位会话。send_reply_to_inbox 每次重试都重新 `find_session_by_name()`。处理完一个新消息后 `break`，不继续遍历旧快照。

---

## 已知限制

以下是客观存在的限制，已在代码中做了最大程度的缓解，但无法完全消除：

### 1. Chrome 必须带 `--remote-debugging-port` 启动

**限制**：CDP 连接的前提条件。如果 Chrome 是正常方式启动的（没带调试端口），脚本无法连接。macOS 升级、Chrome 自动更新后可能需要重新用调试端口启动。

**缓解**：setup.sh 会检测端口是否可用并给出提示。

### 2. Knocket Inbox 登录态会过期

**限制**：脚本本身不处理登录。如果 cookie 过期，页面会跳转到登录页，脚本检测到 0 个会话后会自动 `Page.reload`，但无法自动填写登录信息。

**缓解**：检测到持续 0 会话时日志会明确提示"可能需要重新登录"。建议定期检查日志或配合 Telegram 通知观察。

### 3. macOS 睡眠后 SPA 状态可能丢失

**限制**：Mac 合盖睡眠后，Chrome 后台 tab 的 React SPA 可能进入非活跃状态，DOM 元素丢失。

**缓解**：代码中有 `ensure_page_alive()` 检测，发现 sessions=0 时自动 reload。但 reload 后如果登录态也没了，仍需手动干预。

### 4. 同名会话无法区分

**限制**：脚本用 `session_name`（客户显示名）来定位会话。如果两个客户显示名完全相同，可能导致回复发到错误会话。

**缓解**：Knocket 系统中客户名通常是唯一 ID 或不同名字，实际发生概率极低。

### 5. `Input.insertText` 后 Send 按钮可能仍为 disabled

**限制**：React 控制组件可能不感知 CDP 层面的文字插入，导致 Send 按钮的 disabled 状态不更新。

**缓解**：代码会自动 fallback 到 Enter 键发送。实测 Enter 键方式在 textarea 有 focus 的情况下可靠工作。

---

## File Reference

| File | Purpose |
|---|---|
| `scripts/wecom_auto.py` | **方案 A**：纯 CDP + AI 自动回复 + 企微通知 |
| `scripts/telegram_human.py` | **方案 B**：纯 CDP + Telegram 人工优先 + AI 兜底（推荐） |
| `scripts/setup.sh` | 初始化：创建配置文件、检查前置条件 |
| `assets/config.template.toml` | 配置模板，含所有选项和示例 |
| `references/customization.md` | AI 回复行为和知识库定制指南 |

### 运行时文件（在工作目录中生成）

| File | Purpose |
|---|---|
| `.inbox_state.json` | 消息状态跟踪，防止重复回复 |
| `inbox_monitor.log` | 运行日志 |
