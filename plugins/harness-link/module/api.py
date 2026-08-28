"""harness-link Web API（由核心自动挂载，前缀 /api）。

两组路由：
- 管理面 /api/hlink/*：挂 require_auth，面板登录态访问；
- 客户端 /api/hlink/connector/*：Bearer 令牌自认证（配对令牌 / 会话密钥），
  不走 require_auth —— Harness 客户端不是面板用户。
"""

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from ...web.websec import require_auth
from . import store as ST

router = APIRouter()

_CLIENT_PATH = Path(__file__).with_name("client_stub.py")


def _now():
    return int(time.time())


def _bearer(authorization: str) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def _conn_auth(authorization: str = Header("")):
    """connector 路由依赖：校验 Bearer 会话密钥。"""
    key = _bearer(authorization)
    if not key:
        raise HTTPException(status_code=401, detail="缺少 Bearer 会话密钥")
    async with ST.STORE.lock:
        ST.STORE.ensure_loaded()
        conn = ST.STORE.auth_session(key)
    if conn is None:
        raise HTTPException(status_code=401, detail="会话密钥无效或连接已被吊销")
    return conn


# ================= 管理面 =================

@router.get("/hlink/status")
async def hlink_status(auth=Depends(require_auth)):
    async with ST.STORE.lock:
        ST.STORE.ensure_loaded()
        conns = [ST.STORE.conn_view(c) for c in
                 sorted(ST.STORE.connections.values(), key=lambda c: c["registered_at"])]
        counts = ST.STORE.counts()
    return {"plugin": ST.PLUGIN, "online_window": ST.ONLINE_WINDOW,
            "connections": conns, **counts}


@router.get("/hlink/pairing")
async def hlink_pairing_get(auth=Depends(require_auth)):
    return {"plugin": ST.PLUGIN, **ST.STORE.load_pairing()}


@router.post("/hlink/pairing/rotate")
async def hlink_pairing_rotate(auth=Depends(require_auth)):
    d = await ST.STORE.rotate_pairing()
    return {"plugin": ST.PLUGIN, **d}


@router.post("/hlink/send")
async def hlink_send(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    text = b.get("text", "")
    try:
        text = ST._clean_text(text, "消息内容")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target = str(b.get("conn_id") or "*").strip()
    async with ST.STORE.lock:
        ST.STORE.ensure_loaded()
        if target == "*":
            online = [c for c in ST.STORE.connections.values() if ST.STORE.online(c)]
            ids, skipped = [], []
            for c in online:
                m = ST.STORE.send(c, text)
                ids.append(m["id"])
            skipped = sorted(set(ST.STORE.connections) - {c["id"] for c in online})
            if not online:
                raise HTTPException(status_code=400, detail="当前没有在线的 Harness 连接")
        else:
            c = ST.STORE.connections.get(target)
            if c is None:
                raise HTTPException(status_code=404, detail="连接不存在")
            if not ST.STORE.online(c):
                raise HTTPException(status_code=409,
                                    detail="连接离线（超过心跳窗口），消息不会投递；可稍后重发")
            m = ST.STORE.send(c, text)
            ids = [m["id"]]
            skipped = []
        ST.STORE.cond.notify_all()
    return {"ok": True, "ids": ids, "skipped_offline": skipped}


@router.get("/hlink/messages")
async def hlink_messages(after: int = 0, limit: int = 200, auth=Depends(require_auth)):
    async with ST.STORE.lock:
        ST.STORE.ensure_loaded()
        rows, truncated = ST.STORE.messages_after(after, limit)
        rows = [dict(m) for m in rows]
    return {"messages": rows, "truncated": truncated,
            "cursor": (rows[-1]["id"] if rows else after), "server_time": _now()}


@router.delete("/hlink/connections/{conn_id}")
async def hlink_conn_delete(conn_id: str, auth=Depends(require_auth)):
    async with ST.STORE.lock:
        ST.STORE.ensure_loaded()
        conn = ST.STORE.revoke(conn_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {"ok": True, "revoked": conn_id}


@router.get("/hlink/client-script")
async def hlink_client_script(auth=Depends(require_auth)):
    """下发零依赖 Python 客户端脚本（供 Harness 侧运行）。"""
    try:
        text = _CLIENT_PATH.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"客户端脚本缺失: {e}")
    return Response(
        content=text,
        media_type="text/x-python; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="harness_link_client.py"'},
    )


# ================= Harness 客户端 =================

@router.post("/hlink/connector/register")
async def connector_register(body: dict = None, authorization: str = Header("")):
    token = _bearer(authorization)
    if not ST.STORE.check_pairing(token):
        raise HTTPException(status_code=401, detail="配对令牌无效")
    b = body or {}
    async with ST.STORE.lock:
        ST.STORE.ensure_loaded()
        try:
            conn = ST.STORE.register(b.get("name"), b.get("meta"))
        except OverflowError as e:
            raise HTTPException(status_code=429, detail=str(e))
        ST.STORE.save_state()
    return {"conn_id": conn["id"], "session_key": conn["session_key"],
            "heartbeat_window": ST.ONLINE_WINDOW, "server_time": _now()}


@router.post("/hlink/connector/heartbeat")
async def connector_heartbeat(conn=Depends(_conn_auth)):
    async with ST.STORE.lock:
        if conn["id"] not in ST.STORE.connections:
            raise HTTPException(status_code=401, detail="连接已被吊销")
        ST.STORE.touch(conn)
    return {"ok": True, "online_window": ST.ONLINE_WINDOW}


@router.get("/hlink/connector/poll")
async def connector_poll(wait: int = 15, conn=Depends(_conn_auth)):
    """长轮询取走待投递消息；wait 上限 25 秒。"""
    wait = max(0, min(int(wait), 25))
    deadline = time.monotonic() + wait
    cid = conn["id"]
    async with ST.STORE.lock:
        while True:
            if cid not in ST.STORE.connections:
                raise HTTPException(status_code=401, detail="连接已被吊销")
            ST.STORE.touch(conn)
            msgs = ST.STORE.drain(conn)
            if msgs or deadline - time.monotonic() <= 0:
                return {"messages": msgs, "server_time": _now()}
            remaining = deadline - time.monotonic()
            box = ST.STORE.connections[cid]["outbox"]

            def _has():
                return len(box) > 0

            try:
                await asyncio.wait_for(
                    ST.STORE.cond.wait_for(_has), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                continue


@router.post("/hlink/connector/reply")
async def connector_reply(body: dict = None, conn=Depends(_conn_auth)):
    b = body or {}
    try:
        text = ST._clean_text(b.get("text", ""), "回复内容")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    async with ST.STORE.lock:
        if conn["id"] not in ST.STORE.connections:
            raise HTTPException(status_code=401, detail="连接已被吊销")
        msg = ST.STORE.reply(conn, text)
    return {"ok": True, "id": msg["id"]}
