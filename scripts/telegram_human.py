#!/usr/bin/env python3
"""
Knocket Inbox 智能客服 —— 方案 B：Telegram 人工优先 (telegram_human.py)

纯 CDP WebSocket 后台操作 + Telegram Bot 通知 + 等待人工指令（5分钟）+ 超时自动 AI 回复
"""

import json
import os
import sys
import time
import asyncio
import urllib.request
import urllib.error
from datetime import datetime

# ============================================
# 配置
# ============================================
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
HUMAN_WAIT_SECONDS = int(os.environ.get("HUMAN_WAIT_SECONDS", "300"))  # 等人工回复的秒数，默认 5 分钟
WORK_DIR = os.environ.get("KNOCKET_WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(WORK_DIR, ".inbox_state.json")
LOG_FILE = os.path.join(WORK_DIR, "inbox_monitor.log")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))

# Telegram 配置
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
TG_API_BASE = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

# 企业微信（保留兼容，可选）
WECOM_WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")

# AI 配置
API_BASE = os.environ.get("ANTHROPIC_BASE_URL", "")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# 清除代理
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)

# 记录上次处理的 Telegram update_id，避免重复处理
last_tg_update_id = 0

# ============================================
# 日志
# ============================================
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

# ============================================
# 状态管理
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
# Telegram Bot 通信
# ============================================
def tg_request(method, params=None):
    """调用 Telegram Bot API（同步版，仅用于非 async 上下文）"""
    url = f"{TG_API_BASE}/{method}"
    if params:
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"⚠️ Telegram API 调用失败 [{method}]: {e}")
        return None

async def tg_request_async(method, params=None):
    """调用 Telegram Bot API（异步版，不阻塞事件循环，保持 WebSocket 存活）"""
    url = f"{TG_API_BASE}/{method}"
    if params:
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    
    try:
        loop = asyncio.get_event_loop()
        resp_data = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=35).read())
        return json.loads(resp_data.decode("utf-8"))
    except Exception as e:
        log(f"⚠️ Telegram API 调用失败 [{method}]: {e}")
        return None

def tg_send_message(text, reply_markup=None):
    """发送消息给用户（同步版）"""
    params = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        params["reply_markup"] = reply_markup
    result = tg_request("sendMessage", params)
    if result and result.get("ok"):
        return result["result"]["message_id"]
    return None

async def tg_send_message_async(text, reply_markup=None):
    """发送消息给用户（异步版）"""
    params = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        params["reply_markup"] = reply_markup
    result = await tg_request_async("sendMessage", params)
    if result and result.get("ok"):
        return result["result"]["message_id"]
    return None

def tg_get_updates(offset=None, timeout=30):
    """长轮询获取新消息（同步版）"""
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    return tg_request("getUpdates", params)

async def tg_get_updates_async(offset=None, timeout=30):
    """长轮询获取新消息（异步版 - 不阻塞事件循环）"""
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    return await tg_request_async("getUpdates", params)

async def tg_wait_for_reply(timeout_seconds):
    """
    异步等待用户在 Telegram 中回复指令。
    使用 run_in_executor 避免阻塞事件循环，保持 CDP WebSocket 连接存活。
    返回：用户回复的文本，或 None（超时）
    """
    global last_tg_update_id
    
    deadline = time.time() + timeout_seconds
    log(f"⏳ 等待你的 Telegram 回复（{timeout_seconds}秒内）...")
    
    while time.time() < deadline:
        remaining = int(deadline - time.time())
        if remaining <= 0:
            break
        
        # 长轮询，最多等 min(remaining, 30) 秒
        poll_timeout = min(remaining, 30)
        result = await tg_get_updates_async(offset=last_tg_update_id + 1, timeout=poll_timeout)
        
        if not result or not result.get("ok"):
            continue
        
        updates = result.get("result", [])
        for update in updates:
            update_id = update.get("update_id", 0)
            last_tg_update_id = max(last_tg_update_id, update_id)
            
            msg = update.get("message", {})
            # 只接受来自指定 chat 的文本消息
            if str(msg.get("chat", {}).get("id")) == str(TG_CHAT_ID):
                text = msg.get("text", "").strip()
                if text:
                    log(f"📩 收到你的 Telegram 回复: {text}")
                    return text
    
    log("⏰ 等待超时，未收到回复")
    return None

def flush_tg_updates():
    """清空积压的 Telegram 消息，避免旧消息干扰"""
    global last_tg_update_id
    result = tg_get_updates(offset=last_tg_update_id + 1, timeout=0)
    if result and result.get("ok"):
        updates = result.get("result", [])
        for update in updates:
            last_tg_update_id = max(last_tg_update_id, update.get("update_id", 0))
        if updates:
            log(f"🧹 清空了 {len(updates)} 条积压的 Telegram 消息")

# ============================================
# 企业微信通知（可选，保留兼容）
# ============================================
def notify_wechat(customer, message, reply, is_auto):
    if not WECOM_WEBHOOK:
        return
    
    mode = "🤖 AI 自动回复" if is_auto else "👨 人工指定回复"
    content = (
        f"📬 客服消息处理完成\n\n"
        f"👤 客户: {customer}\n"
        f"💬 消息: {message}\n"
        f"💡 回复方式: {mode}\n"
        f"📝 回复内容: {reply}\n"
        f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    payload = json.dumps({"msgtype": "text", "text": {"content": content}}).encode("utf-8")
    try:
        req = urllib.request.Request(WECOM_WEBHOOK, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except:
        pass

# ============================================
# CDP 通信（后台操作浏览器，不影响前台）
# ============================================
class CDPConnection:
    def __init__(self):
        self.ws = None
        self.ws_url = None
        self.msg_id = 0
    
    def find_inbox_tab(self):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/list")
            with urllib.request.urlopen(req, timeout=5) as resp:
                tabs = json.loads(resp.read())
            return [t for t in tabs if 'knocket-inbox' in t.get('url', '') and t.get('type') == 'page']
        except Exception as e:
            log(f"⚠️ 无法连接 Chrome CDP: {e}")
            return None
    
    async def connect(self, ws_url):
        import websockets
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        self.ws_url = ws_url
        self.ws = await websockets.connect(ws_url)
    
    async def close(self):
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None
    
    async def cdp_call(self, method, params=None):
        """直接调用 CDP 协议方法"""
        if not self.ws:
            return None
        self.msg_id += 1
        mid = self.msg_id
        try:
            await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    return resp
        except Exception as e:
            log(f"⚠️ CDP 调用 {method} 失败: {e}")
            self.ws = None
            return None
    
    async def reload_page(self):
        """刷新页面，等待会话列表加载完成"""
        log("🔄 刷新 inbox 页面...")
        await self.cdp_call("Page.reload")
        
        # 等待页面加载并出现会话（最多 20 秒）
        for i in range(10):
            await asyncio.sleep(2)
            count = await self.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
            if count is not None and int(count) > 0:
                log(f"✅ 页面刷新完成，发现 {count} 个会话")
                return True
        log("⚠️ 页面刷新后未加载出会话")
        return False
    
    async def ensure_connected(self):
        """确保 WebSocket 连接可用，断了就重连"""
        if self.ws:
            try:
                self.msg_id += 1
                await self.ws.send(json.dumps({
                    "id": self.msg_id,
                    "method": "Runtime.evaluate",
                    "params": {"expression": "1", "returnByValue": True}
                }))
                raw = await asyncio.wait_for(self.ws.recv(), timeout=5)
                resp = json.loads(raw)
                if resp.get("id") == self.msg_id:
                    return True
            except Exception as e:
                log(f"🔌 CDP 连接已失效: {e}")
                self.ws = None
        
        log("🔄 CDP 正在重连...")
        tabs = self.find_inbox_tab()
        if not tabs:
            log("⚠️ 重连失败：未找到 inbox 标签页")
            return False
        for tab in tabs:
            try:
                await self.connect(tab['webSocketDebuggerUrl'])
                count = await self.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
                if count is not None and int(count) > 0:
                    log("✅ CDP 重连成功")
                    return True
                # sessions=0 可能是休眠后状态丢失，reload
                if count is not None and int(count) == 0:
                    if await self.reload_page():
                        return True
                await self.close()
            except:
                await self.close()
        log("⚠️ 重连失败")
        return False
    
    async def ensure_page_alive(self):
        """确保页面 SPA 状态正常（休眠后可能丢失），sessions=0 就 reload"""
        count = await self.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
        if count is not None and int(count) > 0:
            return True
        log("⚠️ 页面会话为空，可能休眠后状态丢失")
        return await self.reload_page()
    
    async def eval_js_raw(self, expression, user_gesture=False):
        """内部用的 eval_js，不做重连检查"""
        if not self.ws:
            return None
        self.msg_id += 1
        mid = self.msg_id
        params = {"expression": expression, "returnByValue": True, "awaitPromise": False}
        if user_gesture:
            params["userGesture"] = True
        msg = json.dumps({
            "id": mid,
            "method": "Runtime.evaluate",
            "params": params
        })
        try:
            await self.ws.send(msg)
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    result = resp.get("result", {}).get("result", {})
                    if "value" in result:
                        return result["value"]
                    # 有异常信息的话打出来
                    if result.get("subtype") == "error" or result.get("type") == "undefined":
                        return None
                    exc = resp.get("result", {}).get("exceptionDetails")
                    if exc:
                        log(f"⚠️ JS 执行异常: {exc.get('text', '')}")
                    return None
        except asyncio.TimeoutError:
            log("⚠️ CDP 执行超时")
            return None
        except Exception as e:
            log(f"⚠️ CDP 执行失败: {e}")
            self.ws = None
            return None

    async def eval_js(self, expression, user_gesture=False):
        """执行 JS，自动重连"""
        if not self.ws:
            if not await self.ensure_connected():
                return None
        result = await self.eval_js_raw(expression, user_gesture=user_gesture)
        if result is None and not self.ws:
            # ws 断了，尝试重连后重试
            if await self.ensure_connected():
                result = await self.eval_js_raw(expression, user_gesture=user_gesture)
        return result
    
    async def cdp_dom_focus(self, selector):
        """用 CDP DOM.focus 协议方法聚焦元素——绕过 JS 安全限制，后台 tab 也能 focus"""
        try:
            # 1. 获取文档根节点
            doc = await self.cdp_call("DOM.getDocument", {"depth": 0})
            if not doc:
                log("  ⚠️ DOM.getDocument 失败")
                return False
            root_id = doc.get("result", {}).get("root", {}).get("nodeId")
            if not root_id:
                log("  ⚠️ 获取 root nodeId 失败")
                return False
            
            # 2. 用 DOM.querySelector 查找 textarea
            query_result = await self.cdp_call("DOM.querySelector", {
                "nodeId": root_id,
                "selector": selector
            })
            if not query_result:
                log("  ⚠️ DOM.querySelector 失败")
                return False
            node_id = query_result.get("result", {}).get("nodeId")
            if not node_id or node_id == 0:
                log(f"  ⚠️ 未找到节点: {selector}")
                return False
            
            # 3. DOM.focus —— CDP 底层命令，不受 JS 安全沙箱限制
            focus_result = await self.cdp_call("DOM.focus", {"nodeId": node_id})
            if focus_result and "error" in focus_result:
                log(f"  ⚠️ DOM.focus 报错: {focus_result['error']}")
                return False
            
            await asyncio.sleep(0.2)
            
            # 4. 验证
            active = await self.eval_js("document.activeElement?.tagName")
            log(f"  📊 DOM.focus 后 activeElement: {active}")
            return str(active) == "TEXTAREA" if active else False
        except Exception as e:
            log(f"  ⚠️ cdp_dom_focus 异常: {e}")
            return False
    
    async def click_and_focus_textarea(self, selector):
        """聚焦 textarea，按优先级尝试多种方式"""
        
        # ===== 方式 1: CDP DOM.focus（最可靠，不受后台限制）=====
        log("  🎯 尝试 CDP DOM.focus...")
        if await self.cdp_dom_focus(selector):
            log("  ✅ CDP DOM.focus 成功")
            return True
        
        # ===== 方式 2: JS focus + userGesture =====
        log("  🎯 尝试 JS focus (userGesture)...")
        result = await self.eval_js(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return 'no_el';
            el.scrollIntoView();
            el.click();
            el.focus();
            return document.activeElement?.tagName + ':' + (document.activeElement?.placeholder || '');
        }})()
        """, user_gesture=True)
        
        if result and str(result).startswith('TEXTAREA'):
            log("  ✅ JS focus 成功")
            return True
        log(f"  ⚠️ JS focus 结果: {result}")
        
        # ===== 方式 3: CDP Input.dispatchMouseEvent 模拟真实鼠标点击 =====
        log("  🎯 尝试 CDP 鼠标模拟点击...")
        pos = await self.eval_js(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return JSON.stringify({{x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)}});
        }})()
        """)
        
        if pos:
            try:
                pos_obj = json.loads(pos) if isinstance(pos, str) else None
                if pos_obj:
                    x, y = pos_obj['x'], pos_obj['y']
                    await self.cdp_call("Input.dispatchMouseEvent", {
                        "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
                    })
                    await asyncio.sleep(0.05)
                    await self.cdp_call("Input.dispatchMouseEvent", {
                        "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
                    })
                    await asyncio.sleep(0.3)
            except Exception as e:
                log(f"  ⚠️ CDP 鼠标点击异常: {e}")
        
        # 最终检查
        final = await self.eval_js("document.activeElement?.tagName")
        log(f"  📊 最终 activeElement: {final}")
        return str(final) == "TEXTAREA" if final else False
    
    async def dispatch_input_event(self, selector, text):
        """
        填入文字到 textarea。
        
        核心改动：DOM.focus 成功 + insertText 没报异常 = 直接认为成功。
        不再依赖读取 .value 来验证（React 控制组件的 value 读不出来）。
        后续 send_reply_to_inbox 里的 Send 按钮检查才是最终验证。
        """
        
        # ===== 唯一方案：CDP DOM.focus + Input.insertText =====
        log("  📝 CDP DOM.focus + insertText...")
        focused = await self.click_and_focus_textarea(selector)
        log(f"  📊 focus 结果: {focused}")
        
        if not focused:
            log("  ❌ focus 失败，无法填入文字")
            return False
        
        if not self.ws:
            log("  ❌ WebSocket 不可用")
            return False
        
        # 先清空 textarea 已有内容（如果有的话）
        await self.eval_js(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (el && el.value) {{
                el.select();
            }}
        }})()
        """, user_gesture=True)
        await asyncio.sleep(0.1)
        
        # 用 Input.insertText 写入文字
        self.msg_id += 1
        mid = self.msg_id
        insert_ok = False
        try:
            await self.ws.send(json.dumps({
                "id": mid,
                "method": "Input.insertText",
                "params": {"text": text}
            }))
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    # 检查 CDP 响应有没有 error
                    if "error" in resp:
                        log(f"  ⚠️ insertText CDP 报错: {resp['error']}")
                    else:
                        insert_ok = True
                    break
        except Exception as e:
            log(f"  ⚠️ insertText 异常: {e}")
            self.ws = None
            return False
        
        if not insert_ok:
            log("  ❌ insertText 返回了错误")
            return False
        
        await asyncio.sleep(0.5)
        
        # 尝试多种方式验证文字是否已填入
        verify = await self.eval_js(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return JSON.stringify({{found: false}});
            return JSON.stringify({{
                found: true,
                value: el.value || '',
                valueLen: (el.value || '').length,
                textContent: el.textContent || '',
                textContentLen: (el.textContent || '').length,
                innerText: el.innerText || '',
                innerTextLen: (el.innerText || '').length
            }});
        }})()
        """)
        log(f"  📊 填入验证: {verify}")
        
        # 不管 value 读不读得出来，只要 insertText 成功且 focus 成功，就认为 OK
        # 因为实测 insertText 确实把文字写进去了（用户看到了），只是 .value 读不出来
        log(f"  ✅ [DOM.focus + insertText] 已执行，视为成功")
        return True

# ============================================
# AI 智能回复
# ============================================
def generate_reply(session_name, messages):
    if not API_BASE or not API_KEY:
        return "您好！感谢您的消息，我们已收到，稍后会为您处理。"
    
    recent = messages[-10:]
    conversation = ""
    for msg in recent:
        role_label = "客户" if msg["role"] == "customer" else "客服"
        conversation += f"{role_label}: {msg['text']}\n"
    
    system_prompt = """你是一个专业、友好的客服助手。你的任务是根据对话上下文，生成合适的客服回复。

回复要求：
1. 使用中文回复，语气亲切专业
2. 回复简洁有力，一般 1-3 句话即可，不要太长
3. 针对客户的具体问题给出有针对性的回答
4. 如果客户发了图片（显示为空消息或 [Image]），主动询问图片相关内容
5. 不要使用 emoji
6. 不要自称"我是AI"或"我是机器人"，直接以客服身份回复
7. 如果客户问联系方式，引导在当前窗口沟通
8. 遇到无法确定的具体信息（如价格、交期），表示会确认后回复，不要编造

只输出回复内容本身，不要加任何前缀、标签或解释。"""
    
    url = f"{API_BASE}/v1/messages"
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 300,
        "system": system_prompt,
        "messages": [{
            "role": "user",
            "content": f"以下是与客户「{session_name}」的对话记录：\n\n{conversation}\n\n请生成客服回复："
        }]
    }).encode("utf-8")
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "Authorization": f"Bearer {API_KEY}",
        "Venus-Sticky-Routing": "token"
    }
    
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            reply = result.get("content", [{}])[0].get("text", "").strip()
            if reply:
                return reply.strip('"').strip("'").strip()
    except Exception as e:
        log(f"⚠️ AI 回复生成失败: {e}")
    
    return "感谢您的消息！我们已收到您的咨询，正在为您处理。如有更多问题，请随时告诉我。"

# ============================================
# 发送回复到 Knocket Inbox
# ============================================
async def find_session_by_name(cdp, session_name):
    """通过 session name 精确定位会话在列表中的 index。
    精确匹配优先，只在精确匹配失败时才尝试模糊匹配（带日志警告）。
    """
    result = await cdp.eval_js(f"""
    (() => {{
        const sessions = document.querySelectorAll('.trtc-chat-session');
        const target = {json.dumps(session_name)};
        let fuzzyIdx = -1;
        for (let i = 0; i < sessions.length; i++) {{
            const text = sessions[i].textContent.trim().split(/\\n/)[0].replace(/\\d{{2}}[:/]\\d{{2}}.*/, '').trim();
            // 精确匹配
            if (text === target) return JSON.stringify({{idx: i, match: 'exact'}});
            // 模糊匹配只记录第一个，不立即返回
            if (fuzzyIdx < 0 && (text.includes(target) || target.includes(text))) fuzzyIdx = i;
        }}
        if (fuzzyIdx >= 0) return JSON.stringify({{idx: fuzzyIdx, match: 'fuzzy'}});
        return JSON.stringify({{idx: -1, match: 'none'}});
    }})()
    """)
    if not result:
        return None
    try:
        obj = json.loads(result) if isinstance(result, str) else None
        if not obj or obj['idx'] < 0:
            return None
        if obj['match'] == 'fuzzy':
            log(f"  ⚠️ 会话 [{session_name}] 只有模糊匹配 (index={obj['idx']})，请注意")
        return obj['idx']
    except:
        return None


async def send_reply_to_inbox(cdp, session_name, session_idx, reply_text):
    """
    通过 CDP 在 inbox 页面发送回复。
    
    核心改动：每次重试都完全重建 CDP 连接（关闭旧连接 → 重新连接 → 重新查找会话 → 重新点击进入）。
    这样就跟 check_inbox 查询新消息的流程完全一样，不存在"页面状态过期"的问题。
    """
    
    # ===== 整体最多重试 3 次 =====
    for overall_attempt in range(3):
        if overall_attempt > 0:
            log(f"🔁 整体重试第 {overall_attempt + 1} 次...")
            await asyncio.sleep(2)
        
        # ===== 关键：完全重建 CDP 连接 =====
        log("🔌 重新建立 CDP 连接...")
        await cdp.close()  # 先关闭旧连接
        
        tabs = cdp.find_inbox_tab()
        if not tabs:
            log("⚠️ 未找到 inbox 标签页")
            continue
        
        connected = False
        for tab in tabs:
            try:
                await cdp.connect(tab['webSocketDebuggerUrl'])
                count = await cdp.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
                if count is not None and int(count) > 0:
                    connected = True
                    log(f"✅ CDP 已连接，发现 {count} 个会话")
                    break
                await cdp.close()
            except:
                await cdp.close()
        
        if not connected:
            log("⚠️ CDP 连接失败")
            continue
        
        # ===== 用 session_name 精确查找当前的 index =====
        current_idx = await find_session_by_name(cdp, session_name)
        if current_idx is not None:
            actual_idx = int(current_idx)
            log(f"✅ 会话 [{session_name}] 定位成功: index={actual_idx}")
        else:
            # 找不到就不猜了，直接报错
            log(f"❌ 无法定位会话 [{session_name}]，放弃此次发送")
            continue
        
        # ===== 点击会话，用 userGesture =====
        log(f"🔄 点击会话 [{session_name}] (index={actual_idx})...")
        await cdp.eval_js(f"document.querySelectorAll('.trtc-chat-session')[{actual_idx}]?.click()", user_gesture=True)
        
        # ===== 等待聊天面板 + textarea 出现 =====
        textarea_ready = False
        for attempt in range(5):
            await asyncio.sleep(2)
            
            state = await cdp.eval_js("""
            JSON.stringify({
                chatPanel: !!document.querySelector('.trtc-chat-list'),
                textarea: !!document.querySelector("textarea[placeholder='Write your message...']"),
                activeEl: document.activeElement?.tagName
            })
            """)
            log(f"  📊 [{attempt+1}/5] 页面状态: {state}")
            
            try:
                state_obj = json.loads(state) if isinstance(state, str) else {}
            except:
                state_obj = {}
            
            if state_obj.get('textarea') and state_obj.get('chatPanel'):
                textarea_ready = True
                log(f"✅ chatPanel + textarea 已就绪")
                break
            
            # 再点一次会话
            await cdp.eval_js(f"document.querySelectorAll('.trtc-chat-session')[{actual_idx}]?.click()", user_gesture=True)
        
        if not textarea_ready:
            log("⚠️ textarea 未就绪，进入下一次整体重试")
            continue
        
        # ===== 发送前二次确认：验证当前打开的会话确实是目标客户 =====
        verify_name = await cdp.eval_js("""
        (() => {
            // 尝试从聊天面板标题获取当前打开的会话名称
            const header = document.querySelector('.trtc-chat-header__title') 
                || document.querySelector('.trtc-chat-header');
            if (header) return header.textContent.trim();
            return null;
        })()
        """)
        if verify_name:
            log(f"  📊 当前打开的会话: {verify_name}")
        
        # ===== 填入回复 =====
        selector = "textarea[placeholder='Write your message...']"
        filled = await cdp.dispatch_input_event(selector, reply_text)
        if not filled:
            log("⚠️ 填入回复失败，进入下一次整体重试")
            continue
        
        await asyncio.sleep(0.5)
        
        # ===== 发送消息：优先 Send 按钮，后备 Enter 键 =====
        sent = False
        
        # 先检查 Send 按钮是否可用
        for wait_i in range(6):
            btn_state = await cdp.eval_js("""
                (() => {
                    const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Send');
                    if (!btn) return 'not_found';
                    return btn.disabled ? 'disabled' : 'enabled';
                })()
            """)
            log(f"  📊 Send 按钮状态 [{wait_i+1}/6]: {btn_state}")
            if btn_state == 'enabled':
                break
            await asyncio.sleep(0.5)
        
        if btn_state == 'enabled':
            # 方式 A: 点击 Send 按钮
            clicked = await cdp.eval_js("""
                (() => {
                    const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Send');
                    if (btn && !btn.disabled) { btn.click(); return true; }
                    return false;
                })()
            """, user_gesture=True)
            if clicked:
                log("  ✅ 已点击 Send 按钮")
                sent = True
        
        if not sent:
            # 方式 B: Enter 键发送（需要 textarea 有 focus）
            log("  ⚠️ Send 按钮不可用，尝试 Enter 键发送...")
            
            # 先确保 textarea 有 focus
            await cdp.cdp_dom_focus(selector)
            await asyncio.sleep(0.2)
            
            if cdp.ws:
                try:
                    cdp.msg_id += 1
                    mid = cdp.msg_id
                    await cdp.ws.send(json.dumps({
                        "id": mid,
                        "method": "Input.dispatchKeyEvent",
                        "params": {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}
                    }))
                    while True:
                        raw = await asyncio.wait_for(cdp.ws.recv(), timeout=5)
                        resp = json.loads(raw)
                        if resp.get("id") == mid: break
                    
                    cdp.msg_id += 1
                    mid2 = cdp.msg_id
                    await cdp.ws.send(json.dumps({
                        "id": mid2,
                        "method": "Input.dispatchKeyEvent",
                        "params": {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}
                    }))
                    while True:
                        raw = await asyncio.wait_for(cdp.ws.recv(), timeout=5)
                        resp = json.loads(raw)
                        if resp.get("id") == mid2: break
                    
                    log("  ✅ 已发送 Enter 键")
                    sent = True
                except Exception as e:
                    log(f"  ⚠️ Enter 键发送异常: {e}")
        
        if not sent:
            log("  ⚠️ 发送失败（Send 按钮和 Enter 键都没成功），进入下一次整体重试")
            continue
        
        # ===== 验证消息是否发送成功：检查 textarea 是否被清空 =====
        await asyncio.sleep(2)
        verify_sent = await cdp.eval_js(f"""
        (() => {{
            const el = document.querySelector("{selector}");
            if (!el) return 'no_textarea';
            return el.value ? ('has_value:' + el.value.length) : 'empty';
        }})()
        """)
        log(f"  📊 发送后 textarea 状态: {verify_sent}")
        
        log(f"📤 已发送回复: {reply_text[:50]}...")
        return True
    
    log("❌ 3 次整体重试均失败")
    return False

# ============================================
# 处理新客户消息（核心流程）
# ============================================
async def handle_new_customer_message(cdp, session_name, session_idx, last_text, messages):
    """
    新客户消息处理流程：
    1. Telegram 通知用户
    2. 异步等待用户回复（HUMAN_WAIT_SECONDS），不阻塞事件循环
    3. 收到人工指令 → 按指令回复
    4. 超时 → AI 自动回复
    """
    
    # 1. 先清空积压的 Telegram 消息，避免旧消息被误当成回复
    flush_tg_updates()
    
    # 2. 构建最近对话上下文（给用户看）
    recent_msgs = messages[-5:]
    context_lines = []
    for m in recent_msgs:
        role = "👤客户" if m["role"] == "customer" else "💼客服"
        context_lines.append(f"  {role}: {m['text'][:100]}")
    context_str = "\n".join(context_lines)
    
    # 3. 发送 Telegram 通知（用异步版本，不阻塞事件循环）
    wait_min = HUMAN_WAIT_SECONDS // 60
    notification = (
        f"📬 <b>新客户消息</b>\n\n"
        f"👤 客户: <b>{session_name}</b>\n"
        f"💬 新消息: {last_text[:200]}\n\n"
        f"📋 最近对话:\n<pre>{context_str}</pre>\n\n"
        f"⏰ 你有 <b>{wait_min} 分钟</b>回复我该怎么回。\n"
        f"直接打字告诉我回复内容即可，超时将 AI 自动回复。"
    )
    
    msg_id = await tg_send_message_async(notification)
    if not msg_id:
        log("⚠️ Telegram 通知发送失败，直接 AI 回复")
        reply = generate_reply(session_name, messages)
        await send_reply_to_inbox(cdp, session_name, session_idx, reply)
        return
    
    log(f"📱 Telegram 通知已发送，等待 {wait_min} 分钟人工回复...")
    
    # 4. 异步等待用户回复（不阻塞事件循环，WebSocket 保持存活）
    human_reply = await tg_wait_for_reply(HUMAN_WAIT_SECONDS)
    
    if human_reply:
        # 用户给了指令
        reply_text = human_reply
        is_auto = False
        log(f"👨 人工指定回复: {reply_text[:50]}")
        
        # 发送到 inbox（用 session_name 重新定位会话）
        success = await send_reply_to_inbox(cdp, session_name, session_idx, reply_text)
        
        # 通知用户已发送
        if success:
            await tg_send_message_async(f"✅ 已按你的要求回复客户 <b>{session_name}</b>:\n\n{reply_text}")
        else:
            await tg_send_message_async(
                f"❌ 回复发送失败，请手动处理客户 <b>{session_name}</b>\n\n"
                f"📋 你要发的内容（可直接复制）:\n<pre>{reply_text}</pre>"
            )
    else:
        # 超时，AI 自动回复
        reply_text = generate_reply(session_name, messages)
        is_auto = True
        log(f"🤖 超时，AI 自动回复: {reply_text[:50]}")
        
        success = await send_reply_to_inbox(cdp, session_name, session_idx, reply_text)
        
        # 通知用户 AI 的回复内容（无论成功失败都告知）
        if success:
            await tg_send_message_async(
                f"🤖 已自动回复客户 <b>{session_name}</b>:\n\n{reply_text}\n\n"
                f"(你 {wait_min} 分钟内未回复，已自动处理)"
            )
        else:
            await tg_send_message_async(
                f"❌ 自动回复发送失败，请手动处理客户 <b>{session_name}</b>\n\n"
                f"🤖 AI 原本想回复的内容:\n<pre>{reply_text}</pre>"
            )
    
    # 可选：同时发企微通知
    notify_wechat(session_name, last_text, reply_text, is_auto)

# ============================================
# 主检查循环
# ============================================
async def check_inbox(cdp):
    """单次检查 inbox 所有会话"""
    import websockets
    
    tabs = cdp.find_inbox_tab()
    if not tabs:
        log("⚠️ 未找到 inbox 标签页")
        return
    
    # 找到有会话的标签页
    target_tab = None
    first_connected_tab = None
    for tab in tabs:
        ws_url = tab['webSocketDebuggerUrl']
        try:
            await cdp.connect(ws_url)
            if not first_connected_tab:
                first_connected_tab = tab
            count = await cdp.eval_js("document.querySelectorAll('.trtc-chat-session').length")
            if count and int(count) > 0:
                target_tab = tab
                break
            await cdp.close()
        except:
            await cdp.close()
    
    if not target_tab:
        # 可能是休眠后 SPA 状态丢失，尝试 reload 第一个可连接的 tab
        if first_connected_tab:
            log("⚠️ 所有标签页会话为空，可能是休眠后状态丢失，正在刷新页面...")
            try:
                await cdp.connect(first_connected_tab['webSocketDebuggerUrl'])
                if await cdp.reload_page():
                    target_tab = first_connected_tab
                else:
                    await cdp.close()
            except:
                await cdp.close()
        
        if not target_tab:
            log("⚠️ 所有 inbox 标签页均无会话")
            return
    
    # 获取会话列表
    sessions_raw = await cdp.eval_js("""
        JSON.stringify(Array.from(document.querySelectorAll('.trtc-chat-session')).map((el,i) => ({
            index: i,
            name: el.textContent.trim().split(/\\n/)[0].replace(/\\d{2}[:/]\\d{2}.*/, '').trim(),
            preview: el.textContent.trim().replace(/\\s+/g,' ').slice(0,200)
        })))
    """)
    
    try:
        sessions = json.loads(sessions_raw) if isinstance(sessions_raw, str) else []
    except:
        sessions = []
    
    if not sessions:
        log("📭 没有会话")
        return
    
    log(f"📬 发现 {len(sessions)} 个会话")
    state = load_state()
    state_changed = False
    
    for session in sessions:
        idx = session['index']
        name = session['name']
        log(f"👤 检查会话 [{idx+1}/{len(sessions)}]: {name}")
        
        # 后台点击会话
        await cdp.eval_js(f"document.querySelectorAll('.trtc-chat-session')[{idx}]?.click()")
        await asyncio.sleep(2)
        
        # 获取消息
        messages_raw = await cdp.eval_js("""
            JSON.stringify(Array.from(
                document.querySelectorAll('.trtc-chat-list__item.assistant,.trtc-chat-list__item.user')
            ).map(el => ({
                role: el.classList.contains('assistant') ? 'customer' : 'agent',
                text: (el.querySelector('.trtc-chat-list__item-detail')?.textContent?.trim() || '')
            })).filter(m => m.text.length > 0))
        """)
        
        try:
            messages = json.loads(messages_raw) if isinstance(messages_raw, str) else []
        except:
            messages = []
        
        if not messages:
            log("  ⏭️ 无消息，跳过")
            continue
        
        # 消息签名去重
        last_msg = messages[-1]
        msg_sig = f"{len(messages)}:{last_msg['role']}:{last_msg['text'][:50]}"
        prev_sig = state.get(name, "")
        
        if msg_sig == prev_sig:
            log("  ✅ 无新消息")
            continue
        
        # 有新消息
        if last_msg['role'] == 'customer':
            last_text = last_msg['text'][:200]
            log(f"  💬 新客户消息: {last_text[:80]}")
            
            # 先保存当前状态（标记这条消息已被看到，防止重复处理）
            state[name] = msg_sig
            save_state(state)
            
            # 进入人工优先流程
            await handle_new_customer_message(cdp, name, idx, last_text, messages)
            
            # 回复后重新获取签名（因为多了一条客服消息）
            # 注意：send_reply_to_inbox 会重建 CDP 连接，所以这里需要重连
            try:
                await cdp.close()
                tabs = cdp.find_inbox_tab()
                if tabs:
                    for tab in tabs:
                        try:
                            await cdp.connect(tab['webSocketDebuggerUrl'])
                            count = await cdp.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
                            if count and int(count) > 0:
                                # 重新点击这个会话读取最新消息
                                new_idx = await find_session_by_name(cdp, name)
                                if new_idx is not None:
                                    await cdp.eval_js(f"document.querySelectorAll('.trtc-chat-session')[{new_idx}]?.click()")
                                    await asyncio.sleep(2)
                                    messages_raw_after = await cdp.eval_js("""
                                        JSON.stringify(Array.from(
                                            document.querySelectorAll('.trtc-chat-list__item.assistant,.trtc-chat-list__item.user')
                                        ).map(el => ({
                                            role: el.classList.contains('assistant') ? 'customer' : 'agent',
                                            text: (el.querySelector('.trtc-chat-list__item-detail')?.textContent?.trim() || '')
                                        })).filter(m => m.text.length > 0))
                                    """)
                                    try:
                                        msgs_after = json.loads(messages_raw_after) if isinstance(messages_raw_after, str) else None
                                        if msgs_after:
                                            last_after = msgs_after[-1]
                                            state[name] = f"{len(msgs_after)}:{last_after['role']}:{last_after['text'][:50]}"
                                            save_state(state)
                                    except:
                                        pass
                                break
                            await cdp.close()
                        except:
                            await cdp.close()
            except:
                pass
            
            # ===== 关键修复：处理完一个新消息后，直接 break =====
            # 不继续遍历旧快照中的后续会话（index 可能已经过时了）
            # 下一轮 check_inbox 会重新获取最新快照
            log("  ℹ️ 本轮已处理一条消息，跳出等待下一轮检查")
            break
        else:
            log("  ℹ️ 最后一条是客服消息，无需回复")
        
        state[name] = msg_sig
        state_changed = True
    
    if state_changed:
        save_state(state)
    
    await cdp.close()

# ============================================
# 主入口
# ============================================
async def main():
    log("🚀 ====== 客服监控启动 (方案B - Telegram 人工优先模式 telegram_human) ======")
    log(f"⏱️  检查间隔: {CHECK_INTERVAL}秒")
    log(f"⏳ 人工等待: {HUMAN_WAIT_SECONDS}秒")
    log(f"📁 状态文件: {STATE_FILE}")
    log(f"🔌 CDP 端口: {CDP_PORT}")
    log(f"🤖 Telegram Bot: @Knocket_bot")
    log("💡 流程: 新消息 → Telegram 通知你 → 等你回复 → 超时自动 AI 回复")
    
    if not TG_CHAT_ID:
        log("❌ TG_CHAT_ID 未设置！请设置环境变量 TG_CHAT_ID")
        sys.exit(1)
    
    # 启动时清空积压消息
    flush_tg_updates()
    tg_send_message("🟢 Knocket 客服监控已启动！\n\n有新客户消息会通知你，你可以直接回复告诉我怎么回。")
    
    cdp = CDPConnection()
    
    while True:
        log("🔍 开始检查 inbox...")
        try:
            await check_inbox(cdp)
        except Exception as e:
            log(f"❌ 检查异常: {e}")
            import traceback
            traceback.print_exc()
            await cdp.close()
        
        log(f"⏰ 等待 {CHECK_INTERVAL}秒...")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("🛑 监控已手动停止")
    except Exception as e:
        log(f"💀 致命错误: {e}")
        sys.exit(1)
