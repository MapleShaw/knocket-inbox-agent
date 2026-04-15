# 踩坑记录 & 常见问题

> 从零到跑通，踩过的每一个坑都在这里。

---

## 坑 1：Chrome 必须用调试模式启动，普通启动没用

**现象：** 脚本报 `CDP 连接失败` 或 `ECONNREFUSED 127.0.0.1:9222`

**原因：** 脚本通过 Chrome DevTools Protocol (CDP) 控制浏览器，Chrome 默认不开放这个端口。

**解决：** 关掉所有 Chrome 窗口，再用以下命令重新启动：

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\tmp\chrome-debug

# Linux
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

> ⚠️ `--user-data-dir` 建议用一个临时目录，避免影响你日常 Chrome 的登录状态。

---

## 坑 2：必须手动打开对话详情页，脚本不会自己点

**现象：** 脚本一直输出"未找到打开的对话详情页"

**原因：** 脚本通过检测页面上有没有 `textarea[placeholder='Write your message...']` 来判断是否在对话页，不会自动点击会话列表。

**解决：** 在 Chrome 里打开 [Knocket Inbox](https://console.trtc.io/knocket-inbox)，手动点进一个对话，保持这个页面在浏览器里打开。

---

## 坑 3：AI 调用一直报 401 / 403

**常见原因：**
1. `AI_API_KEY` 填错或过期
2. `AI_BASE_URL` 末尾多了 `/v1`（脚本会自动拼接 `/v1/chat/completions`，填了就变成 `/v1/v1/...`）
3. `AI_MODEL` 模型名和 API 提供商不匹配

**排查步骤：**
```bash
# 直接用 curl 测一下 key 是否有效
curl https://api.siliconflow.cn/v1/chat/completions \
  -H "Authorization: Bearer $AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-ai/DeepSeek-V3","messages":[{"role":"user","content":"hi"}]}'
```

**解决：** 确认 `.env` 里 `AI_PROVIDER=openai`，`AI_BASE_URL` 不带 `/v1` 后缀。

---

## 坑 4：AI API 推荐用哪个？

国内用户推荐 **SiliconFlow**（免费额度，DeepSeek V3）：

```
AI_BASE_URL=https://api.siliconflow.cn
AI_API_KEY=sk-xxx   # 注册 siliconflow.cn 获取
AI_MODEL=deepseek-ai/DeepSeek-V3
AI_PROVIDER=openai
```

注册地址：https://siliconflow.cn

---

## 坑 5：React 页面 DOM 结构很难捉摸

**现象：** 读取消息内容为空，或发送按钮找不到

**原因：** Knocket Inbox 是 React 应用，DOM 是动态渲染的，普通 `querySelector` 有时拿不到正确节点，且 class 名会随版本变化。

**现状（已稳定的选择器）：**
```javascript
// 消息列表
document.querySelectorAll('.trtc-chat-list__item')

// 消息文本
el.querySelector('.trtc-chat-list__item-text-inner, .trtc-chat-list__item-text, .trtc-chat-list__item-detail-inner')

// 输入框
textarea[placeholder='Write your message...']

// 发送按钮
Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Send')
```

> ⚠️ 如果 Knocket 升级了前端版本，这些选择器可能失效，需要重新 inspect。

---

## 坑 6：发送消息用 `Input.insertText` 而不是 `keyboard.type`

**现象：** 用模拟键盘输入中文时乱码，或内容填进去了但 Send 按钮还是灰的

**原因：** React 的 `onChange` 事件不响应模拟键盘事件，`Input.insertText` 才能触发正确的事件流。

**解决：** 已在 `knocket_monitor.py` 里用 CDP 的 `Input.insertText` + `DOM.focus` 组合实现。

---

## 坑 7：Send 按钮点了没反应

**现象：** 日志显示"Send button clicked"但消息没发出去

**原因：** React 的 `button.click()` 有时需要 `userGesture: true` 才能触发，且按钮有防抖，刚填完字马上点可能还是 disabled 状态。

**解决：** 已实现重试逻辑——填字后等 0.2s，最多重试 6 次点击，失败则降级用 Enter 键发送。

---

## 坑 8：Windows 上没有 `.sh` 启动脚本

**解决：** 用 `scripts/start.ps1`，逻辑和 `start.sh` 完全一致，从 `scripts/.env` 读取配置。

```powershell
# 第一次使用
cp scripts\.env.example scripts\.env
# 编辑 .env 填入配置
.\scripts\start.ps1
```

---

## 坑 9：`.env` 文件被 git 追踪导致 API Key 泄露

**解决：** 项目根目录的 `.gitignore` 已排除 `scripts/.env`，只保留 `scripts/.env.example`。

**自查：**
```bash
git status  # 确认 .env 没有出现在 tracked files 里
```

---

## 坑 10：状态文件导致重复通知 / 漏通知

**现象：** 同一条消息反复收到通知，或新消息没有触发通知

**原因：** 状态靠 `scripts/.inbox_state.json` 去重，如果这个文件损坏或内容异常会出问题。

**解决：** 删掉重来：
```bash
rm scripts/.inbox_state.json
```

---

## 常见问题速查

| 问题 | 原因 | 解决 |
|------|------|------|
| `CDP 连接失败` | Chrome 没用调试模式启动 | 见坑 1 |
| `未找到对话详情页` | 没在浏览器里打开对话 | 见坑 2 |
| AI 回复 401/403 | API Key 或 Header 格式错误 | 见坑 3 |
| AI 回复为空 | `AI_BASE_URL` / `AI_MODEL` 填错 | 检查 `.env` |
| 消息读取为空 | DOM 选择器失效（Knocket 升级了） | 见坑 5 |
| 发送没反应 | Send 按钮 disabled / React 事件问题 | 见坑 6、7 |
| 重复通知 | state 文件异常 | 见坑 10 |
