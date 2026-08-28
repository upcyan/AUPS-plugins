"""harness-link 状态存储与业务逻辑。

授权模型（两级令牌）：
- 配对令牌 pairing token：管理员在「接入授权」页查看/轮换，客户端仅用于 register
  一次性换取会话密钥；
- 会话密钥 session key：register 成功后签发，是该连接后续所有通信的凭证，
  可被管理员随时吊销。

消息模型：
- out（面板 -> Harness）：进入连接待投递队列，客户端长轮询取走；
- in （Harness -> 面板）：客户端 reply 上行，前端按游标增量拉取。

持久化：
- <data>/state.json       连接注册表 + 消息计数器 + 待投递队列（原子写）
- <data>/transcript.jsonl 追加式消息历史（超限轮转，仅用于回看）
- <config>/pairing.json   配对令牌

并发：所有可变状态由 asyncio.Lock 保护；长轮询经 asyncio.Condition 等待唤醒。
"""

import asyncio
import json
import logging
import os
import secrets
import time
from collections import deque
from hmac import compare_digest

from ... import config

PLUGIN = "harness-link"

ONLINE_WINDOW = 90                     # 心跳窗口（秒），超过视为离线
MAX_CONNECTIONS = 20                   # 连接数上限
MAX_TEXT = 32 * 1024                   # 单条消息最大字节数
MAX_OUTBOX = 200                       # 单连接待投递队列深度上限
MAX_RECENT = 500                       # 内存保留的最近消息条数
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024 # 历史文件轮转阈值
MAX_META_BYTES = 4 * 1024              # 客户端元数据上限
LOG = logging.getLogger(__name__)


def now():
    return int(time.time())


def _clean_text(text, what):
    if not isinstance(text, str) or not text.strip():
        raise ValueError(what + " 不能为空")
    if len(text.encode("utf-8")) > MAX_TEXT:
        raise ValueError(what + " 过长（上限 32KB）")
    return text


def _clean_name(name):
    name = str(name or "").strip()
    if not name:
        name = "harness-client"
    name = "".join(ch for ch in name if ch.isprintable())[:64]
    return name or "harness-client"


def _clean_meta(meta):
    """元数据只收一层扁平 dict，限制大小。"""
    if not isinstance(meta, dict):
        return {}
    out = {}
    for k, v in list(meta.items())[:20]:
        if not isinstance(k, str) or len(k) > 64:
            continue
        if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 512:
            out[k] = v
    if len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > MAX_META_BYTES:
        return {}
    return out


class Store:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.cond = asyncio.Condition(self.lock)
        self.connections = {}   # id -> conn
        self.recent = []        # 最近消息（内存权威），旧消息看 jsonl
        self.next_id = 1
        self.loaded = False

    # ---------- 路径 ----------
    def state_path(self):
        return os.path.join(config.plugin_dir(PLUGIN, "data"), "state.json")

    def transcript_path(self):
        return os.path.join(config.plugin_dir(PLUGIN, "data"), "transcript.jsonl")

    def pairing_path(self):
        return os.path.join(config.plugin_dir(PLUGIN, "config"), "pairing.json")

    # ---------- 加载 / 保存 ----------
    def ensure_loaded(self):
        if self.loaded:
            return
        try:
            with open(self.state_path(), encoding="utf-8") as f:
                st = json.load(f)
            self.next_id = int(st.get("next_id", 1))
            for cid, c in (st.get("connections") or {}).items():
                box = deque(c.get("outbox") or [], MAX_OUTBOX)
                self.connections[cid] = {
                    "id": cid,
                    "name": _clean_name(c.get("name")),
                    "meta": _clean_meta(c.get("meta")),
                    "session_key": c.get("session_key") if isinstance(c.get("session_key"), str) else "",
                    "registered_at": int(c.get("registered_at", 0)),
                    "last_seen": int(c.get("last_seen", 0)),
                    "outbox": box,
                    "sent": int(c.get("sent", 0)),
                    "recv": int(c.get("recv", 0)),
                }
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            LOG.warning("harness-link state load failed; starting with empty state: %s", exc)
            pass
        try:
            lines = []
            with open(self.transcript_path(), encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except ValueError:
                            continue
            self.recent = lines[-MAX_RECENT:]
            if self.recent:
                self.next_id = max(self.next_id, self.recent[-1].get("id", 0) + 1)
        except OSError:
            pass
        self.loaded = True

    def save_state(self):
        data = {
            "next_id": self.next_id,
            "connections": {
                cid: {
                    "name": c["name"], "meta": c["meta"],
                    "session_key": c["session_key"],
                    "registered_at": c["registered_at"], "last_seen": c["last_seen"],
                    "outbox": list(c["outbox"]),
                    "sent": c["sent"], "recv": c["recv"],
                } for cid, c in self.connections.items()
            },
        }
        path = self.state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _append_transcript(self, msg):
        try:
            path = self.transcript_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path) and os.path.getsize(path) > MAX_TRANSCRIPT_BYTES:
                os.replace(path, path + ".1")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _emit(self, direction, conn, text, delivered=False):
        msg = {
            "id": self.next_id,
            "dir": direction,             # out: 面板->Harness; in: Harness->面板
            "conn": conn["id"],
            "name": conn["name"],
            "text": text,
            "ts": now(),
            "delivered": delivered,
        }
        self.next_id += 1
        self.recent.append(msg)
        if len(self.recent) > MAX_RECENT:
            self.recent = self.recent[-MAX_RECENT:]
        self._append_transcript(msg)
        return msg

    # ---------- 配对令牌 ----------
    def load_pairing(self):
        try:
            with open(self.pairing_path(), encoding="utf-8") as f:
                d = json.load(f)
            if d.get("token"):
                return {"token": d["token"], "created_at": int(d.get("created_at", 0))}
        except (OSError, ValueError, TypeError):
            pass
        path = self.pairing_path()
        d = {"token": secrets.token_urlsafe(24), "created_at": now()}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return d

    async def rotate_pairing(self):
        d = {"token": secrets.token_urlsafe(24), "created_at": now()}
        async with self.lock:
            os.makedirs(os.path.dirname(self.pairing_path()), exist_ok=True)
            tmp = self.pairing_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, self.pairing_path())
            try:
                os.chmod(self.pairing_path(), 0o600)
            except OSError:
                pass
        return d

    def check_pairing(self, token):
        d = self.load_pairing()
        return bool(token) and compare_digest(str(token), str(d["token"]))

    # ---------- 连接 ----------
    def online(self, conn):
        return (now() - int(conn.get("last_seen", 0))) <= ONLINE_WINDOW

    def conn_view(self, conn):
        return {
            "id": conn["id"],
            "name": conn["name"],
            "meta": conn["meta"],
            "online": self.online(conn),
            "registered_at": conn["registered_at"],
            "last_seen": conn["last_seen"],
            "pending": len(conn["outbox"]),
            "sent": conn["sent"],
            "recv": conn["recv"],
        }

    def register(self, name, meta):
        if len(self.connections) >= MAX_CONNECTIONS:
            raise OverflowError("连接数已达上限（%d），请先吊销不用的连接" % MAX_CONNECTIONS)
        cid = "hl-" + secrets.token_hex(6)
        conn = {
            "id": cid,
            "name": _clean_name(name),
            "meta": _clean_meta(meta),
            "session_key": secrets.token_urlsafe(24),
            "registered_at": now(),
            "last_seen": now(),
            "outbox": deque(maxlen=MAX_OUTBOX),
            "sent": 0,
            "recv": 0,
        }
        self.connections[cid] = conn
        return conn

    def auth_session(self, key):
        for conn in self.connections.values():
            if conn["session_key"] and compare_digest(conn["session_key"], key):
                return conn
        return None

    def touch(self, conn):
        conn["last_seen"] = now()

    def drain(self, conn):
        """取走待投递消息（标记已投递）。"""
        msgs = []
        while conn["outbox"]:
            m = conn["outbox"].popleft()
            m["delivered"] = True
            msgs.append({"id": m["id"], "text": m["text"], "ts": m["ts"]})
        if msgs:
            conn["sent"] += len(msgs)
            self.save_state()
        return msgs

    def send(self, conn, text):
        msg = self._emit("out", conn, text)
        if len(conn["outbox"]) >= MAX_OUTBOX:
            conn["outbox"].popleft()   # 队列满丢弃最老，保留最新指令
        conn["outbox"].append(msg)
        return msg

    def reply(self, conn, text):
        conn["recv"] += 1
        return self._emit("in", conn, text, delivered=True)

    def revoke(self, cid):
        conn = self.connections.pop(cid, None)
        if conn is not None:
            self.save_state()
        return conn

    def messages_after(self, after, limit=200):
        limit = max(1, min(int(limit), 500))
        rows = [m for m in self.recent if m.get("id", 0) > after]
        truncated = False
        if rows and rows[0]["id"] > after + 1 and after >= 0:
            # 游标之前的更早历史已滚出内存窗口
            truncated = True
        return rows[:limit], truncated

    def counts(self):
        conns = list(self.connections.values())
        return {
            "connections_total": len(conns),
            "online": sum(1 for c in conns if self.online(c)),
            "messages": (self.recent[-1]["id"] if self.recent else 0),
        }


STORE = Store()
