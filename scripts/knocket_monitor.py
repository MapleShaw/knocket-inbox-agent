#!/usr/bin/env python3
"""
Knocket Inbox 客服监控 - OpenClaw 微信通知版
- CDP 后台监听 Knocket Inbox（你手动打开对话详情页）
- 新消息 → 微信通知（通过 OpenClaw API）
- 5分钟等你人工回复，超时自动 AI 回复
"""

import json
import os
import sys
import time
import asyncio
import urllib.request
from datetime import datetime

# ---- 导入通知模块 ----
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openclaw_notify import send_wx_message_async, wait_for_wx_reply, send_wx_message

# ============================================
# 配置
# ============================================
CHECK_INTERVAL     = int(os.environ.get("CHECK_INTERVAL", "60"))
HUMAN_WAIT_SECONDS = int(os.environ.get("HUMAN_WAIT_SECONDS", "300"))
WORK_DIR           = os.environ.get("KNOCKET_WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
STATE_FILE         = os.path.join(WORK_DIR, ".inbox_state.json")
LOG_FILE           = os.path.join(WORK_DIR, "inbox_monitor.log")
CDP_PORT           = int(os.environ.get("CDP_PORT", "9222"))

# AI 配置
AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai")
API_BASE    = os.environ.get("AI_BASE_URL", "")
API_KEY     = os.environ.get("AI_API_KEY", "")
MODEL       = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-4.6")

for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(k, None)

# ============================================
# 日志
# ============================================
def log(msg):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

# ============================================
# 状态
# ============================================
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"⚠️ 保存状态失败: {e}")

# ============================================
# AI 回复
# ============================================
def generate_reply(session_name, messages):
    if not API_BASE or not API_KEY:
        return "您好！感谢您的消息，我们已收到，稍后为您处理。"

    recent = messages[-10:]
    conversation = "".join(
        f"{'客户' if m['role']=='customer' else '客服'}: {m['text']}\n"
        for m in recent
    )
    system_prompt = (
        "你是专业友好的客服。中文回复，简洁 1-3 句，不要使用 emoji，不要自称 AI，"
        "不确定的信息说会确认后回复，只输出回复内容本身。"
    )
    url     = f"{API_BASE.rstrip('/')}/v1/chat/completions"
    payload = json.dumps({
        "model":    MODEL,
        "max_tokens": 300,
        "messages": [
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": f"客户「{session_name}」对话：\n{conversation}\n请生成回复："}
        ]
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {API_KEY}"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            text = result["choices"][0]["message"]["content"].strip()
            return text.strip('"').strip("'").strip()
    except Exception as e:
        log(f"⚠️ AI 回复失败: {e}")
    return "感谢您的咨询！我们已收到，正在为您处理。"

# ============================================
# CDP 连接
# ============================================
class CDPConnection:
    def __init__(self):
        self.ws     = None
        self.ws_url = None
        self.msg_id = 0

    def find_tabs(self):
        """列出所有 page 类型标签页（不过滤 URL，由调用方判断是否有 textarea）"""
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/list")
            with urllib.request.urlopen(req, timeout=5) as r:
                tabs = json.loads(r.read())
            return [t for t in tabs if t.get("type") == "page"]
        except Exception as e:
            log(f"⚠️ CDP 连接失败: {e}")
            return []

    async def connect(self, ws_url):
        import websockets
        if self.ws:
            try: await self.ws.close()
            except: pass
            self.ws = None
        self.ws_url = ws_url
        try:
            self.ws = await websockets.connect(ws_url)
        except Exception as e:
            log(f"⚠️ WebSocket 连接失败: {e}")
            self.ws = None

    async def close(self):
        if self.ws:
            try: await self.ws.close()
            except: pass
            self.ws = None

    async def eval_js(self, expr, user_gesture=False):
        if not self.ws:
            return None
        self.msg_id += 1
        mid = self.msg_id
        params = {"expression": expr, "returnByValue": True, "awaitPromise": False}
        if user_gesture:
            params["userGesture"] = True
        try:
            await self.ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate", "params": params}))
            while True:
                raw  = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    result = resp.get("result", {}).get("result", {})
                    return result.get("value")
        except Exception as e:
            log(f"⚠️ eval_js 失败: {e}")
            self.ws = None
            return None

    async def cdp_call(self, method, params=None):
        if not self.ws:
            return None
        self.msg_id += 1
        mid = self.msg_id
        try:
            await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                raw  = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    return resp
        except Exception as e:
            log(f"⚠️ cdp_call {method} 失败: {e}")
            self.ws = None
            return None

    async def focus_and_type(self, selector, text):
        """聚焦 textarea 并填入文字"""
        doc = await self.cdp_call("DOM.getDocument", {"depth": 0})
        if doc:
            root_id = doc.get("result", {}).get("root", {}).get("nodeId")
            if root_id:
                q = await self.cdp_call("DOM.querySelector", {"nodeId": root_id, "selector": selector})
                if q:
                    node_id = q.get("result", {}).get("nodeId")
                    if node_id:
                        await self.cdp_call("DOM.focus", {"nodeId": node_id})
                        await asyncio.sleep(0.2)
        if not self.ws:
            return False
        self.msg_id += 1
        mid = self.msg_id
        try:
            await self.ws.send(json.dumps({"id": mid, "method": "Input.insertText", "params": {"text": text}}))
            while True:
                raw  = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    return True
        except Exception as e:
            log(f"⚠️ insertText 失败: {e}")
            self.ws = None
            return False

    async def click_send_button(self, textarea_selector):
        """点击 Send 按钮"""
        for _ in range(6):
            state = await self.eval_js("""
                (() => {
                    const btn = Array.from(document.querySelectorAll('button'))
                                    .find(b => b.textContent.trim() === 'Send');
                    if (!btn) return 'not_found';
                    return btn.disabled ? 'disabled' : 'enabled';
                })()
            """)
            if state == "enabled":
                clicked = await self.eval_js("""
                    (() => {
                        const btn = Array.from(document.querySelectorAll('button'))
                                        .find(b => b.textContent.trim() === 'Send');
                        if (btn && !btn.disabled) { btn.click(); return true; }
                        return false;
                    })()
                """, user_gesture=True)
                if clicked:
                    return True
            await asyncio.sleep(0.5)
        # fallback: Enter 键
        if self.ws:
            for evt_type in ["keyDown", "keyUp"]:
                self.msg_id += 1
                await self.ws.send(json.dumps({
                    "id": self.msg_id, "method": "Input.dispatchKeyEvent",
                    "params": {"type": evt_type, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}
                }))
                await asyncio.sleep(0.1)
            return True
        return False


# ============================================
# 核心：找到有 textarea 的标签页并发送回复
# ============================================
async def send_reply(reply_text):
    """
    直接在当前打开的对话页找 textarea 填字发送。
    不点击任何会话，不切换页面。
    """
    selector = "textarea[placeholder='Write your message...']"
    cdp = CDPConnection()

    tabs = cdp.find_tabs()
    if not tabs:
        log("⚠️ 找不到 Knocket 标签页，请确保浏览器已打开")
        return False

    # 找有 textarea 的标签页
    target_tab = None
    for tab in tabs:
        await cdp.connect(tab["webSocketDebuggerUrl"])
        # 用固定 id=9999 直接发原始请求，避免 eval_js msg_id 冲突
        has_textarea = False
        if cdp.ws:
            try:
                import asyncio as _aio
                await cdp.ws.send(__import__('json').dumps({"id": 9999, "method": "Runtime.evaluate",
                    "params": {"expression": "document.querySelector(\"textarea[placeholder='Write your message...']\") !== null", "returnByValue": True}}))
                deadline = _aio.get_event_loop().time() + 5
                while _aio.get_event_loop().time() < deadline:
                    raw = await _aio.wait_for(cdp.ws.recv(), timeout=5)
                    resp = __import__('json').loads(raw)
                    if resp.get("id") == 9999:
                        has_textarea = resp.get("result", {}).get("result", {}).get("value") is True
                        break
            except Exception as e:
                log(f"⚠️ 检查 textarea 失败: {e}")
        if has_textarea:
            target_tab = tab
            break
        await cdp.close()

    if not target_tab:
        log("⚠️ 没有找到打开的对话详情页（找不到 textarea），请手动打开一个对话")
        return False

    # 直接填字发送
    filled = await cdp.focus_and_type(selector, reply_text)
    if not filled:
        log("⚠️ 填字失败")
        await cdp.close()
        return False

    await asyncio.sleep(0.5)
    sent = await cdp.click_send_button(selector)
    await cdp.close()

    if sent:
        log(f"✅ 回复已发送: {reply_text[:80]}")
        return True
    else:
        log("⚠️ 发送按钮点击失败")
        return False


# ============================================
# 核心：读取当前对话页的消息列表
# ============================================
async def read_current_messages():
    """读取当前打开的对话详情页的消息列表和会话名"""
    cdp = CDPConnection()
    tabs = cdp.find_tabs()
    if not tabs:
        return None, []

    target_tab = None
    for tab in tabs:
        await cdp.connect(tab["webSocketDebuggerUrl"])
        has_textarea = False
        if cdp.ws:
            try:
                import json as _json
                await cdp.ws.send(_json.dumps({"id": 9999, "method": "Runtime.evaluate",
                    "params": {"expression": "document.querySelectorAll('textarea').length > 0", "returnByValue": True}}))
                import asyncio as _aio
                deadline = _aio.get_event_loop().time() + 5
                while _aio.get_event_loop().time() < deadline:
                    raw = await _aio.wait_for(cdp.ws.recv(), timeout=5)
                    resp = _json.loads(raw)
                    if resp.get("id") == 9999:
                        has_textarea = resp.get("result", {}).get("result", {}).get("value") is True
                        break
            except Exception as e:
                log(f"⚠️ 检查 textarea 失败: {e}")
        if has_textarea:
            target_tab = tab
            break
        await cdp.close()

    if not target_tab:
        await cdp.close()
        return None, []

    # 读取会话名
    session_name = await cdp.eval_js("""
        (() => {
            const active = document.querySelector('.trtc-chat-session.is-active .trtc-chat-session__main-top');
            if (active) return active.textContent.trim();
            const title = document.querySelector('.trtc-chat-session__main-top');
            if (title) return title.textContent.trim();
            return 'visitor';
        })()
    """) or "visitor"

    # 读取消息列表
    msgs_raw = await cdp.eval_js("""
        JSON.stringify((() => {
            const items = document.querySelectorAll('.trtc-chat-list__item');
            return Array.from(items).map(el => {
                const cls = el.className || '';
                const isCustomer = cls.includes('assistant');  // assistant=访客, user=客服
                const textEl = el.querySelector('.trtc-chat-list__item-text-inner, .trtc-chat-list__item-text, .trtc-chat-list__item-detail-inner');
                const text = textEl ? textEl.textContent.trim() : '';
                return { role: isCustomer ? 'customer' : 'agent', text };
            }).filter(m => m.text);
        })()
    )""")

    messages = []
    try:
        messages = json.loads(msgs_raw) if msgs_raw else []
    except:
        pass

    await cdp.close()
    return session_name, messages

# ============================================
# 处理新消息
# ============================================
_pending = False

async def handle_new_message(session_name, last_text, messages):
    global _pending
    wait_min = HUMAN_WAIT_SECONDS // 60

    recent = messages[-5:]
    ctx = "\n".join(
        f"  {'👤客户' if m['role']=='customer' else '💼客服'}: {m['text'][:100]}"
        for m in recent
    )
    notif = (
        f"📬 新客户消息\n\n"
        f"👤 客户: {session_name}\n"
        f"💬 新消息: {last_text[:200]}\n\n"
        f"📋 最近对话:\n{ctx}\n\n"
        f"⏰ {wait_min} 分钟内回复，超时 AI 自动处理。\n"
        f"📝 回复格式：[Knocket] 你的回复内容"
    )
    await send_wx_message_async(notif)
    log(f"📱 微信通知已发送，等待 {wait_min} 分钟...")

    human_reply = await wait_for_wx_reply(HUMAN_WAIT_SECONDS, log_fn=log)

    if human_reply:
        reply_text = human_reply
        log(f"👨 人工回复: {reply_text[:60]}")
    else:
        reply_text = generate_reply(session_name, messages)
        log(f"🤖 AI 自动回复: {reply_text[:60]}")

    try:
        success = await asyncio.wait_for(send_reply(reply_text), timeout=30)
    except asyncio.TimeoutError:
        log("⚠️ send_reply 超时30秒")
        success = False

    # 无论成功失败，都标记 state，防止重复触发
    state = load_state()
    state["current"] = f"handled:{last_text[:80]}"
    save_state(state)

    if success:
        who = "人工" if human_reply else f"AI（{wait_min}分钟无回复）"
        await send_wx_message_async(f"✅ {who}已回复客户 {session_name}:\n\n{reply_text}")
    else:
        await send_wx_message_async(f"❌ 回复发送失败，请手动处理\n\n要发的内容:\n{reply_text}")

    _pending = False


# ============================================
# 主检查循环
# ============================================
async def check_inbox():
    global _pending

    if _pending:
        log("⏳ 正在处理上一条消息，跳过本次检查")
        return

    session_name, messages = await read_current_messages()

    if session_name is None:
        log("⚠️ 未找到打开的对话详情页，请在浏览器中打开 Knocket 对话")
        return

    if not messages:
        log(f"  [{session_name}] 📭 暂无消息")
        return

    # 找最后一条客户消息
    last_customer_msg = None
    for m in reversed(messages):
        if m["role"] == "customer":
            last_customer_msg = m
            break

    if not last_customer_msg:
        log(f"  [{session_name}] ℹ️ 没有客户消息")
        return

    last_text = last_customer_msg["text"].strip()
    state = load_state()
    prev = state.get("current", "")

    # 如果上一次是我们发出的这条回复，说明已处理
    if prev == f"handled:{last_text[:80]}":
        log(f"  [{session_name}] ✅ 无新消息（最后是我们的回复）")
        return

    sig = f"lastMsg:{last_text[:80]}"
    if sig == prev:
        log(f"  [{session_name}] ✅ 无新消息")
        return

    # 新的客户消息
    state["current"] = sig
    save_state(state)

    log(f"  [{session_name}] 💬 新消息: {last_text[:80]}")
    _pending = True
    asyncio.create_task(handle_new_message(session_name, last_text, messages))


# ============================================
# 入口
# ============================================
async def main():
    log("🚀 ===== Knocket 客服监控启动 =====")
    log(f"⏱️  检查间隔: {CHECK_INTERVAL}s  |  人工等待: {HUMAN_WAIT_SECONDS}s")
    log("📌 请在浏览器中手动打开 Knocket 对话详情页，脚本不会切换页面")

    send_wx_message("🟢 Knocket 客服监控已启动！\n有新消息我会通知你，直接回复告诉我怎么回就行。")

    while True:
        log("🔍 检查 inbox...")
        try:
            await check_inbox()
        except Exception as e:
            log(f"❌ 异常: {e}")
        log(f"⏰ 等待 {CHECK_INTERVAL}s...")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("🛑 已停止")
    except Exception as e:
        log(f"💀 致命错误: {e}")
        sys.exit(1)
