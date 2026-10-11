"""调试会话与审计：限时、随机令牌、只存哈希、即时吊销、操作留痕。

安全取舍：
- 令牌用 secrets.token_urlsafe(32) 生成，落盘只存 SHA-256，比较用
  compare_digest；即使数据文件泄露也无法还原令牌。
- TTL 强制夹在 MIN_TTL..MAX_TTL，避免误设长期有效授权。
- 会话可限定 roots / commands，收紧到「本次只需读这些目录、用这些命令」。
- 审计只记命令、结果与来源，不记令牌与输出正文，避免审计本身成为泄露源。
"""

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time

from ...errors import AppError

MIN_TTL = 60
MAX_TTL = 8 * 3600
DEFAULT_TTL = 3600
_FILE = "sessions.json"
_AUDIT = "audit.jsonl"
_AUDIT_KEEP = 500


def _base(base=None):
    if base:
        return base
    from ... import config
    return config.plugin_dir("remotedebug", "data")


def _path(name, base=None):
    directory = _base(base)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, name)


def hash_token(token):
    """令牌哈希（落盘与比较都用它）。"""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _load(base=None):
    try:
        with open(_path(_FILE, base), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"sessions": []}
    except (OSError, ValueError):
        return {"sessions": []}


def _save(data, base=None):
    path = _path(_FILE, base)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".sessions-",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _prune(data, now=None):
    now = now if now is not None else time.time()
    sessions = [s for s in data.get("sessions", [])
                if not s.get("revoked") and float(s.get("expires_at") or 0) > now]
    data["sessions"] = sessions
    return data


def create_session(label, ttl_seconds=DEFAULT_TTL, roots=None, commands=None,
                   note="", base=None):
    """创建调试会话，返回 {token, session}；token 只在此刻返回一次。"""
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL
    ttl = max(MIN_TTL, min(ttl, MAX_TTL))
    token = secrets.token_urlsafe(32)
    now = time.time()
    session = {
        "sid": secrets.token_hex(8),
        "label": str(label or "调试会话")[:64],
        "note": str(note or "")[:200],
        "created_at": int(now),
        "expires_at": int(now) + ttl,
        "ttl_seconds": ttl,
        "token_hash": hash_token(token),
        "roots": [str(r) for r in (roots or [])],
        "commands": [str(c) for c in (commands or [])],
        "revoked": False,
        "uses": 0,
    }
    data = _prune(_load(base))
    data.setdefault("sessions", []).append(session)
    _save(data, base)
    return {"token": token, "session": {k: v for k, v in session.items()
                                        if k != "token_hash"}}


def list_sessions(base=None):
    """列出有效会话（不含令牌哈希）。"""
    data = _prune(_load(base))
    return [{k: v for k, v in s.items() if k != "token_hash"}
            for s in data.get("sessions", [])]


def verify_token(token, base=None):
    """校验令牌；有效则返回会话并累加使用次数，否则 None。"""
    if not token:
        return None
    now = time.time()
    data = _prune(_load(base))
    digest = hash_token(token)
    for session in data.get("sessions", []):
        if hmac.compare_digest(session.get("token_hash", ""), digest):
            session["uses"] = int(session.get("uses") or 0) + 1
            session["last_used_at"] = int(now)
            _save(data, base)
            return {k: v for k, v in session.items() if k != "token_hash"}
    return None


def revoke_session(sid, base=None):
    """立即吊销会话（不等待自然过期）。"""
    data = _load(base)
    hit = None
    for session in data.get("sessions", []):
        if session.get("sid") == sid:
            session["revoked"] = True
            session["revoked_at"] = int(time.time())
            hit = session
    if hit is None:
        raise AppError(f"调试会话不存在：{sid}")
    _prune(data)
    _save(data, base)
    return {"sid": sid, "revoked": True}


def revoke_all(base=None):
    """全部吊销（应急用）。"""
    data = _load(base)
    n = 0
    for session in data.get("sessions", []):
        if not session.get("revoked"):
            session["revoked"] = True
            session["revoked_at"] = int(time.time())
            n += 1
    _save({"sessions": []} if n else data, base)
    return {"revoked": n}


def _set_expiry_for_test(sid, expires_at, base=None):
    """仅供测试：直接设置过期时间以验证过期拒绝路径。"""
    data = _load(base)
    for session in data.get("sessions", []):
        if session.get("sid") == sid:
            session["expires_at"] = int(expires_at)
    _save(data, base)


def record_audit(session, command, ok, exit_code=None, duration_ms=None,
                 output_bytes=None, ip=None, redactions=None, note="", base=None):
    """记录一次调用；命令原文可能含敏感值，先脱敏再落盘。"""
    from . import redact as R
    row = {
        "ts": int(time.time()),
        "sid": (session or {}).get("sid", ""),
        "label": (session or {}).get("label", ""),
        "ip": str(ip or "")[:64],
        "command": R.redact(str(command or ""))[:500],
        "ok": bool(ok),
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "output_bytes": output_bytes,
        "redactions": redactions,
        "note": str(note or "")[:200],
    }
    path = _path(_AUDIT, base)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _trim_audit(path)
    return row


def _trim_audit(path, keep=_AUDIT_KEEP):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) <= keep:
        return
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".audit-",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(lines[-keep:])
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def audit_log(limit=200, base=None):
    """最近审计记录（新→旧）。"""
    path = _path(_AUDIT, base)
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    limit = max(1, min(int(limit or 200), _AUDIT_KEEP))
    return list(reversed(rows[-limit:]))
