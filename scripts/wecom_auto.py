#!/usr/bin/env python3
"""
Knocket Inbox 智能客服 —— 方案 A：企微全自动 (wecom_auto.py)

纯 CDP WebSocket 后台操作 + AI 自动回复 + 企业微信群通知

核心特性：
- 纯 CDP WebSocket 直连，不依赖任何 CLI 工具，不影响浏览器使用
- 新消息 → AI 立即自动回复 → 企微群通知你
- CDP 踩坑修复全覆盖（DOM.focus、insertText、Enter 键兜底、会话名定位等）
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
WORK_DIR = os.environ.get("KNOCKET_WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(WORK_DIR, ".inbox_state.json")
LOG_FILE = os.path.join(WORK_DIR, "inbox_monitor.log")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))

WECOM_WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")  # 企业微信 Webhook URL

# AI 配置
API_BASE = os.environ.get("ANTHROPIC_BASE_URL", "")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# 清除代理
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)

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
# 企业微信通知
# ============================================
def notify_wechat(customer, message, reply):
    if not WECOM_WEBHOOK:
        return
    
    content = (
        f"📬 新客户消息通知\n\n"
        f"👤 客户: {customer}\n"
        f"💬 消息: {message}\n"
        f"🤖 已自动回复: {reply}\n"
        f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    payload = json.dumps({
        "msgtype": "text",
        "text": {"content": content}
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(
            WECOM_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
        log("📱 微信通知已发送")
    except Exception as e:
        log(f"⚠️ 微信通知失败: {e}")


# ============================================
# CDP 通信（核心：直连标签页，不影响前台）
# 同步自 v3 的所有踩坑修复
# ============================================
class CDPConnection:
    """通过 WebSocket 直接与指定标签页通信，完全不影响用户的浏览器操作"""
    
    def __init__(self):
        self.ws = None
        self.ws_url = None
        self.msg_id = 0
    
    def find_inbox_tab(self):
        """通过 CDP HTTP 接口找到 inbox 标签页的 WebSocket URL"""
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/list")
            with urllib.request.urlopen(req, timeout=5) as resp:
                tabs = json.loads(resp.read())
            return [t for t in tabs if 'knocket-inbox' in t.get('url', '') and t.get('type') == 'page']
        except Exception as e:
            log(f"⚠️ 无法连接 Chrome CDP: {e}")
            return None
    
    async def connect(self, ws_url):
        """连接到指定标签页"""
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
        
        for i in range(10):
            await asyncio.sleep(2)
            count = await self.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
            if count is not None and int(count) > 0:
                log(f"✅ 页面刷新完成，发现 {count} 个会话")
                return True
        log("⚠️ 页面刷新后未加载出会话（可能需要重新登录）")
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
        msg = json.dumps({"id": mid, "method": "Runtime.evaluate", "params": params})
        try:
            await self.ws.send(msg)
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
                    result = resp.get("result", {}).get("result", {})
                    if "value" in result:
                        return result["value"]
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
            if await self.ensure_connected():
                result = await self.eval_js_raw(expression, user_gesture=user_gesture)
        return result
    
    async def cdp_dom_focus(self, selector):
        """用 CDP DOM.focus 协议方法聚焦元素——绕过 JS 安全限制，后台 tab 也能 focus"""
        try:
            doc = await self.cdp_call("DOM.getDocument", {"depth": 0})
            if not doc:
                log("  ⚠️ DOM.getDocument 失败")
                return False
            root_id = doc.get("result", {}).get("root", {}).get("nodeId")
            if not root_id:
                log("  ⚠️ 获取 root nodeId 失败")
                return False
            
            query_result = await self.cdp_call("DOM.querySelector", {
                "nodeId": root_id, "selector": selector
            })
            if not query_result:
                log("  ⚠️ DOM.querySelector 失败")
                return False
            node_id = query_result.get("result", {}).get("nodeId")
            if not node_id or node_id == 0:
                log(f"  ⚠️ 未找到节点: {selector}")
                return False
            
            focus_result = await self.cdp_call("DOM.focus", {"nodeId": node_id})
            if focus_result and "error" in focus_result:
                log(f"  ⚠️ DOM.focus 报错: {focus_result['error']}")
                return False
            
            await asyncio.sleep(0.2)
            active = await self.eval_js("document.activeElement?.tagName")
            log(f"  📊 DOM.focus 后 activeElement: {active}")
            return str(active) == "TEXTAREA" if active else False
        except Exception as e:
            log(f"  ⚠️ cdp_dom_focus 异常: {e}")
            return False
    
    async def click_and_focus_textarea(self, selector):
        """聚焦 textarea，按优先级尝试多种方式"""
        
        # 方式 1: CDP DOM.focus（最可靠）
        log("  🎯 尝试 CDP DOM.focus...")
        if await self.cdp_dom_focus(selector):
            log("  ✅ CDP DOM.focus 成功")
            return True
        
        # 方式 2: JS focus + userGesture
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
        
        # 方式 3: CDP 鼠标模拟点击
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
        
        final = await self.eval_js("document.activeElement?.tagName")
        log(f"  📊 最终 activeElement: {final}")
        return str(final) == "TEXTAREA" if final else False
    
    async def dispatch_input_event(self, selector, text):
        """
        填入文字到 textarea。
        核心：DOM.focus 成功 + insertText 没报异常 = 视为成功。
        不依赖 .value 验证（React 控制组件读不出来）。
        """
        log("  📝 CDP DOM.focus + insertText...")
        focused = await self.click_and_focus_textarea(selector)
        log(f"  📊 focus 结果: {focused}")
        
        if not focused:
            log("  ❌ focus 失败，无法填入文字")
            return False
        
        if not self.ws:
            log("  ❌ WebSocket 不可用")
            return False
        
        # 先清空已有内容
        await self.eval_js(f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (el && el.value) {{ el.select(); }}
        }})()
        """, user_gesture=True)
        await asyncio.sleep(0.1)
        
        # Input.insertText 写入
        self.msg_id += 1
        mid = self.msg_id
        insert_ok = False
        try:
            await self.ws.send(json.dumps({
                "id": mid, "method": "Input.insertText", "params": {"text": text}
            }))
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=15)
                resp = json.loads(raw)
                if resp.get("id") == mid:
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
        log(f"  ✅ [DOM.focus + insertText] 已执行，视为成功")
        return True


# ============================================
# AI 智能回复
# ============================================
def generate_reply(session_name, messages):
    """调用大模型生成智能回复"""
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
# 通过 session_name 精确定位会话
# ============================================
async def find_session_by_name(cdp, session_name):
    """精确匹配优先，模糊匹配兜底"""
    result = await cdp.eval_js(f"""
    (() => {{
        const sessions = document.querySelectorAll('.trtc-chat-session');
        const target = {json.dumps(session_name)};
        let fuzzyIdx = -1;
        for (let i = 0; i < sessions.length; i++) {{
            const text = sessions[i].textContent.trim().split(/\\n/)[0].replace(/\\d{{2}}[:/]\\d{{2}}.*/, '').trim();
            if (text === target) return JSON.stringify({{idx: i, match: 'exact'}});
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


# ============================================
# 发送回复到 Knocket Inbox（含 3 次整体重试）
# ============================================
async def send_reply_to_inbox(cdp, session_name, session_idx, reply_text):
    """
    通过 CDP 在 inbox 页面发送回复。
    每次重试都完全重建 CDP 连接，避免页面状态过期。
    """
    
    for overall_attempt in range(3):
        if overall_attempt > 0:
            log(f"🔁 整体重试第 {overall_attempt + 1} 次...")
            await asyncio.sleep(2)
        
        # 完全重建 CDP 连接
        log("🔌 重新建立 CDP 连接...")
        await cdp.close()
        
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
        
        # 用 session_name 精确查找
        current_idx = await find_session_by_name(cdp, session_name)
        if current_idx is not None:
            actual_idx = int(current_idx)
            log(f"✅ 会话 [{session_name}] 定位成功: index={actual_idx}")
        else:
            log(f"❌ 无法定位会话 [{session_name}]，放弃此次发送")
            continue
        
        # 点击会话
        log(f"🔄 点击会话 [{session_name}] (index={actual_idx})...")
        await cdp.eval_js(f"document.querySelectorAll('.trtc-chat-session')[{actual_idx}]?.click()", user_gesture=True)
        
        # 等待 chatPanel + textarea
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
            
            await cdp.eval_js(f"document.querySelectorAll('.trtc-chat-session')[{actual_idx}]?.click()", user_gesture=True)
        
        if not textarea_ready:
            log("⚠️ textarea 未就绪，进入下一次整体重试")
            continue
        
        # 发送前确认当前打开的会话
        verify_name = await cdp.eval_js("""
        (() => {
            const header = document.querySelector('.trtc-chat-header__title') 
                || document.querySelector('.trtc-chat-header');
            if (header) return header.textContent.trim();
            return null;
        })()
        """)
        if verify_name:
            log(f"  📊 当前打开的会话: {verify_name}")
        
        # 填入回复
        selector = "textarea[placeholder='Write your message...']"
        filled = await cdp.dispatch_input_event(selector, reply_text)
        if not filled:
            log("⚠️ 填入回复失败，进入下一次整体重试")
            continue
        
        await asyncio.sleep(0.5)
        
        # 发送：优先 Send 按钮，后备 Enter 键
        sent = False
        
        btn_state = 'unknown'
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
            # Enter 键兜底
            log("  ⚠️ Send 按钮不可用，尝试 Enter 键发送...")
            await cdp.cdp_dom_focus(selector)
            await asyncio.sleep(0.2)
            
            if cdp.ws:
                try:
                    cdp.msg_id += 1
                    mid = cdp.msg_id
                    await cdp.ws.send(json.dumps({
                        "id": mid, "method": "Input.dispatchKeyEvent",
                        "params": {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}
                    }))
                    while True:
                        raw = await asyncio.wait_for(cdp.ws.recv(), timeout=5)
                        resp = json.loads(raw)
                        if resp.get("id") == mid: break
                    
                    cdp.msg_id += 1
                    mid2 = cdp.msg_id
                    await cdp.ws.send(json.dumps({
                        "id": mid2, "method": "Input.dispatchKeyEvent",
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
            log("  ⚠️ 发送失败，进入下一次整体重试")
            continue
        
        # 验证
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
# 主循环
# ============================================
async def check_inbox(cdp):
    """单次检查 inbox 所有会话"""
    import websockets
    
    tabs = cdp.find_inbox_tab()
    if not tabs:
        log("⚠️ 未找到 inbox 标签页，请确保 Chrome 中已打开 knocket-inbox")
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
        except Exception as e:
            log(f"⚠️ 连接标签页失败: {e}")
            await cdp.close()
    
    if not target_tab:
        # 休眠后 SPA 状态可能丢失，尝试 reload
        if first_connected_tab:
            log("⚠️ 所有标签页会话为空，尝试刷新页面...")
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
        
        # 后台点击该会话
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
        
        # 检查最后一条是否来自客户
        if last_msg['role'] == 'customer':
            last_text = last_msg['text'][:200]
            log(f"  💬 新客户消息: {last_text[:80]}")
            
            # 先保存状态防止重复处理
            state[name] = msg_sig
            save_state(state)
            
            # 生成智能回复
            reply = generate_reply(name, messages)
            
            if reply:
                log(f"  🤖 智能回复: {reply[:80]}")
                
                # 发送回复
                success = await send_reply_to_inbox(cdp, name, idx, reply)
                
                if success:
                    # 发送微信通知
                    notify_wechat(name, last_text, reply)
                else:
                    log(f"  ❌ 回复发送失败，需要手动处理客户 [{name}]")
                    # 即使发送失败也通知企微
                    if WECOM_WEBHOOK:
                        notify_wechat(name, last_text, f"[发送失败] 原本想回复: {reply}")
            
            # 回复后重新获取签名
            try:
                await cdp.close()
                tabs = cdp.find_inbox_tab()
                if tabs:
                    for tab in tabs:
                        try:
                            await cdp.connect(tab['webSocketDebuggerUrl'])
                            count = await cdp.eval_js_raw("document.querySelectorAll('.trtc-chat-session').length")
                            if count and int(count) > 0:
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
            
            # 处理完一个新消息后 break，下一轮重新获取最新快照
            log("  ℹ️ 本轮已处理一条消息，跳出等待下一轮检查")
            break
        else:
            log("  ℹ️ 最后一条是客服消息，无需回复")
        
        state[name] = msg_sig
        state_changed = True
    
    if state_changed:
        save_state(state)
    
    await cdp.close()


async def main():
    log("🚀 ====== 客服监控启动 (方案A - 企微全自动模式 wecom_auto) ======")
    log(f"⏱️  检查间隔: {CHECK_INTERVAL}秒")
    log(f"📁 状态文件: {STATE_FILE}")
    log(f"🔌 CDP 端口: {CDP_PORT}")
    log(f"📱 企微通知: {'已配置' if WECOM_WEBHOOK else '未配置'}")
    log("💡 流程: 新消息 → AI 自动回复 → 企微通知你")
    log("💡 本版本使用纯 CDP 协议，不会占用你的浏览器窗口")
    
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
