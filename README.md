# Knocket Inbox Agent

一行代码嵌入网页的 AI 智能客服——基于 [Knocket](https://console.trtc.io/knocket-inbox) 聊天组件，自动回复客户消息，实时通知到你的微信、企业微信或 Telegram。

## 这是什么？

[Knocket](https://console.trtc.io/knocket-inbox) 是一个免费的网页聊天小组件，一行代码就能在你的网站右下角加一个聊天气泡。这个项目在 Knocket 的基础上加了一层 AI 智能客服能力：

- 🤖 客户发消息 → AI 自动回复
- 📱 同时通知到你的手机（微信 / 企业微信 / Telegram）
- 👆 支持人工接管：你觉得 AI 回得不对，随时自己上
- ⏱️ 可配置等待时间，超时才触发 AI 兜底

## 三种模式

**方案 A：企微全自动**
> 客户发消息 → AI 立即回复 → 企微群通知你
>
> 适合量大、标准化咨询的场景

**方案 B：Telegram 人工优先**
> 客户发消息 → Telegram 通知你 → 你回复/不回复 → 超时 AI 自动兜底
>
> 适合重要客户、需要人工把关的场景

**方案 C：微信人工优先（OpenClaw）⭐ 推荐**
> 客户发消息 → 微信通知你 → 你回复/不回复 → 超时 AI 自动兜底
>
> 适合国内用户、微信重度使用者，通过 [OpenClaw](https://openclaw.ai) 发送微信通知

## 前置要求

- Python 3.8+ 及 `websockets` 库：`pip3 install websockets`
- **Chrome 浏览器**，需用调试模式启动（见下方）
- 方案 A 需要：企业微信群机器人 Webhook
- 方案 B 需要：Telegram Bot Token + Chat ID
- 方案 C 需要：[OpenClaw](https://openclaw.ai) CLI + 微信插件

## 快速开始

### 第一步：Clone 仓库

```bash
git clone https://github.com/MapleShaw/knocket-inbox-agent.git
cd knocket-inbox-agent
```

### 第二步：配置环境变量

```bash
cp scripts/.env.example scripts/.env
# 编辑 scripts/.env，填入你的 API Key 等配置
```

`.env` 文件已加入 `.gitignore`，不会被提交，API Key 安全。

### 第三步：用调试模式启动 Chrome

> ⚠️ 这步很重要，普通方式启动的 Chrome 脚本连不上。

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-debug

# Windows（PowerShell）
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir=C:\tmp\chrome-debug

# Linux
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

### 第四步：打开 Knocket 并进入对话页

在刚启动的 Chrome 里打开 [Knocket Inbox](https://console.trtc.io/knocket-inbox)，登录后**手动点开一个对话**（脚本不会自动切换页面）。

### 第五步：启动脚本

**macOS / Linux：**
```bash
bash scripts/start.sh
```

**Windows（PowerShell）：**
```powershell
.\scripts\start.ps1
```

查看日志确认运行正常：
```bash
tail -f scripts/inbox_monitor.log
```

## AI API 推荐

支持任意 OpenAI 兼容 API。国内推荐 **SiliconFlow**（免费额度，接 DeepSeek V3）：

1. 注册：https://siliconflow.cn
2. 获取 API Key
3. 在 `.env` 里填入：
```
AI_BASE_URL=https://api.siliconflow.cn
AI_API_KEY=sk-xxx
AI_MODEL=deepseek-ai/DeepSeek-V3
AI_PROVIDER=openai
```

## 文件结构

```
knocket-inbox-agent/
├── README.md                        # 你正在看的这个
├── SKILL.md                         # 详细技术文档（AI Agent 使用）
├── scripts/
│   ├── .env.example                 # 环境变量模板 ← 从这里开始
│   ├── start.sh                     # macOS/Linux 启动脚本
│   ├── start.ps1                    # Windows 启动脚本
│   ├── knocket_monitor.py           # 方案 C 核心（OpenClaw 微信通知版）
│   ├── openclaw_notify.py           # OpenClaw 通知模块
│   ├── wecom_auto.py                # 方案 A：企微全自动
│   ├── telegram_human.py            # 方案 B：Telegram 人工优先
│   ├── wechat_human.py              # 方案 C 备用：iLink Bot 微信版
│   └── setup.sh                     # 依赖安装脚本
├── assets/
│   └── config.template.toml         # 配置模板（参考用）
└── references/
    ├── troubleshooting.md           # 踩坑记录 ← 遇到问题先看这里
    ├── usage-guide.md               # 详细使用指南
    └── customization.md             # AI 回复定制指南
```

## 遇到问题？

先看 [踩坑记录](references/troubleshooting.md)，覆盖了从 CDP 连接失败到 React DOM 选择器失效的 10 个常见问题。

## 背景故事

这个项目是用 Vibe Coding 做出来的——从零到跑通，踩了一地坑（CDP 后台操作 React 页面的各种奇葩问题），最后全都解决了。详细的技术细节在 `SKILL.md` 里。

## License

MIT
