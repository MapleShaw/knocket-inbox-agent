"""
OpenClaw 通知模块：替代原 wechat_human.py 的微信 iLink Bot API
通过本地 OpenClaw /tools/invoke HTTP API 发消息给管理员微信
"""

import json
import os
import time
import asyncio
import urllib.request
import urllib.error

# ============================================
# OpenClaw 通知配置（替换 iLink Bot）
# ============================================
OPENCLAW_API_URL = os.environ.get("OPENCLAW_API_URL", "http://127.0.0.1:23001/tools/invoke")
OPENCLAW_TOKEN   = os.environ.get("OPENCLAW_TOKEN", "a3f9477ed94471e9b8df9e914d9a6c1a44a2fd8d68a52d00")
WX_TARGET        = os.environ.get("WX_TARGET", "o9cq804B5NFzgeH1SfUjLdgbgP50@im.wechat")
WX_ACCOUNT_ID    = os.environ.get("WX_ACCOUNT_ID", "032f1f8d89df-im-bot")

# 等待人工回复的 session key（微信 session）
WX_SESSION_KEY   = os.environ.get("WX_SESSION_KEY", "agent:main:openclaw-weixin:direct:o9cq804b5nfzgeh1sfujldgbgp50@im.wechat")

# 回复消息的轮询间隔（秒）
POLL_INTERVAL    = int(os.environ.get("POLL_INTERVAL", "5"))

def _openclaw_call(tool, args):
    """调用 OpenClaw /tools/invoke API"""
    payload = json.dumps({
        "tool": tool,
        "args": args,
        "sessionKey": WX_SESSION_KEY
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENCLAW_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENCLAW_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False), result.get("result", {})
    except Exception as e:
        return False, {"error": str(e)}

def send_wx_message(text: str) -> bool:
    """发送微信消息给管理员"""
    ok, result = _openclaw_call("message", {
        "action": "send",
        "channel": "openclaw-weixin",
        "accountId": WX_ACCOUNT_ID,
        "target": WX_TARGET,
        "message": text
    })
    return ok

async def send_wx_message_async(text: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: send_wx_message(text))

def _get_session_messages():
    """获取微信 session 全部消息，返回 (count, last_user_text)"""
    ok, result = _openclaw_call("sessions_history", {
        "sessionKey": WX_SESSION_KEY,
        "limit": 20,
        "includeTools": False
    })
    if not ok:
        return 0, None
    try:
        content = result.get("content", [{}])[0].get("text", "{}")
        data = json.loads(content)
        messages = data.get("messages", [])
        if not messages:
            return 0, None
        last = messages[-1]
        role = last.get("role")
        raw_content = last.get("content", "")
        if isinstance(raw_content, list):
            text = " ".join(
                item.get("text", "") for item in raw_content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()
        else:
            text = str(raw_content).strip()
        return len(messages), (text if role == "user" else None)
    except:
        return 0, None

async def wait_for_wx_reply(timeout_seconds: int, log_fn=None) -> str | None:
    """
    轮询微信 session，等待管理员回复（用消息数量判断新增）。
    返回回复文本，或 None（超时）。
    """
    if log_fn is None:
        log_fn = print

    # 记录当前消息总数作为 baseline
    baseline_count, _ = _get_session_messages()
    log_fn(f"⏳ 等待你的微信回复（最多 {timeout_seconds // 60} 分钟，当前消息数={baseline_count}）...")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        count, last_user_text = _get_session_messages()
        if count > baseline_count and last_user_text:
            log_fn(f"📩 收到消息（消息数 {baseline_count}→{count}）: {last_user_text[:80]}")
            # 只认 [Knocket] 前缀的回复
            import re
            m = re.match(r'\[Knocket\]\s*(.*)', last_user_text, re.DOTALL)
            if m:
                reply = m.group(1).strip()
                log_fn(f"✅ Knocket 指令: {reply[:80]}")
                return reply
            else:
                log_fn(f"⏭️ 非 Knocket 指令，忽略，继续等待...")
                baseline_count = count  # 更新 baseline，继续等下一条

    log_fn("⏰ 等待超时，未收到回复")
    return None
