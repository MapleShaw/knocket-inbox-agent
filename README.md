# Knocket Inbox Agent

一行代码嵌入网页的 AI 智能客服——基于 [Knocket](https://console.trtc.io/knocket-inbox) 聊天组件，自动回复客户消息，实时通知到你的企业微信或 Telegram。

## 这是什么？

[Knocket](https://console.trtc.io/knocket-inbox) 是一个免费的网页聊天小组件，一行代码就能在你的网站右下角加一个聊天气泡。这个 Skill 在 Knocket 的基础上加了一层 AI 智能客服能力：

- 🤖 客户发消息 → AI 自动回复
- 📱 同时通知到你的手机（企业微信 / Telegram）
- 👆 支持人工接管：你觉得 AI 回得不对，随时自己上

## 两种模式

**方案 A：企微全自动**
> 客户发消息 → AI 立即回复 → 企微群通知你
>
> 适合量大、标准化咨询的场景

**方案 B：Telegram 人工优先 ⭐ 推荐**
> 客户发消息 → Telegram 通知你 → 你回复/不回复 → 5 分钟没回 AI 自动兜底
>
> 适合重要客户、需要人工把关的场景

## 怎么用？

### 第一步：Clone 仓库

```bash
git clone https://github.com/fangxinmoon/knocket-inbox-agent.git
cd knocket-inbox-agent
```

### 第二步：启动

1. 用调试端口启动 Chrome：
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
   ```

2. 在 Chrome 中打开 [Knocket Inbox](https://console.trtc.io/knocket-inbox) 并登录

3. 设置环境变量并启动：
   ```bash
   # 方案 A（企微）
   export WECOM_WEBHOOK="你的企微群机器人 Webhook URL"
   export AI_PROVIDER="anthropic"    # 或 "openai"（兼容 DeepSeek/通义千问/智谱等）
   export AI_BASE_URL="你的 AI API 地址"
   export AI_API_KEY="你的 API Key"
   export AI_MODEL="你的模型名"      # 如 claude-haiku-4-5-20251001 / gpt-4o-mini / deepseek-chat
   export KNOCKET_WORK_DIR="$(pwd)"
   nohup python3 scripts/wecom_auto.py > /dev/null 2>&1 &

   # 方案 B（Telegram）
   export TG_BOT_TOKEN="你的 Telegram Bot Token"
   export TG_CHAT_ID="你的 Chat ID"
   export AI_PROVIDER="anthropic"    # 或 "openai"
   export AI_BASE_URL="你的 AI API 地址"
   export AI_API_KEY="你的 API Key"
   export AI_MODEL="你的模型名"
   export KNOCKET_WORK_DIR="$(pwd)"
   nohup python3 scripts/telegram_human.py > /dev/null 2>&1 &
   ```

4. 查看日志确认运行正常：
   ```bash
   tail -f inbox_monitor.log
   ```

## 前置要求

- Python 3 + `websockets` 库（`pip3 install websockets`）
- Chrome 浏览器（需用 `--remote-debugging-port=9222` 启动）
- 方案 A 需要：企业微信群机器人 Webhook
- 方案 B 需要：Telegram Bot Token + Chat ID

## 文件结构

```
knocket-inbox-agent/
├── SKILL.md                         # Skill 定义文件（详细技术文档）
├── README.md                        # 你正在看的这个（给人读的）
├── scripts/
│   ├── wecom_auto.py                # 方案 A：企微全自动
│   ├── telegram_human.py            # 方案 B：Telegram 人工优先
│   └── setup.sh                     # 初始化脚本
├── assets/
│   └── config.template.toml         # 配置模板
└── references/
    ├── usage-guide.md               # 详细使用指南
    └── customization.md             # AI 回复定制指南
```

## 背景故事

这个 Skill 是一个非技术同学用 Vibe Coding 做出来的——从零到跑通，踩了一地坑（CDP 后台操作 React 页面的各种奇葩问题），最后全都解决了。详细的踩坑过程和技术细节都在 `SKILL.md` 里。

## License

MIT
