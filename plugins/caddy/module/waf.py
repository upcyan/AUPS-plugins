"""WAF 规则库（与具体反代无关）：规则增删改、IP 黑/白名单、限流、订阅（远程规则源）。

规则存储在 /etc/aups/waf.json。反代后端（rproxy.caddy 等）通过 render_config()
拿到中性结构后渲染成自己的配置片段，因此更换反代程序无需改动本模块。

规则类型 kinds：
  path_regex  — 请求路径正则，pattern 为正则
  user_agent  — User-Agent 正则，pattern 为正则
  header      — 请求头正则，field 为头名、pattern 为正则
  method      — 请求方法，pattern 如 GET/POST
  query       — 查询参数，field 为参数名、pattern 为值（支持 * 通配）
"""

import hashlib
import ipaddress
import json
import os
import re
import time
import urllib.request

from . import env
from ...errors import AppError

KINDS = ("path_regex", "user_agent", "header", "method", "query")
_WINDOW_RE = re.compile(r"^\d+(ms|s|m|h|d)?$")


# ---------- 读写 ----------

def _load():
    path = env.WAF_FILE
    if os.path.isfile(path):
        try:
            return json.load(open(path))
        except (OSError, ValueError):
            pass
    return {"enabled": True, "blacklist_ips": [], "whitelist_ips": [],
            "rules": [], "subscriptions": [],
            "rate_limit": {"enabled": False, "requests": 60, "window": "10s"}}


def _save(data):
    os.makedirs(config.CONF_DIR, exist_ok=True)
    with open(env.WAF_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(env.WAF_FILE, 0o600)


# ---------- 校验 ----------

def _valid_ip(value):
    try:
        ipaddress.ip_network(value.strip(), strict=False)
        return True
    except ValueError:
        return False


def _validate_rule(kind, pattern, field):
    if kind not in KINDS:
        raise AppError(f"未知规则类型：{kind}（可选：{'、'.join(KINDS)}）")
    if not pattern or not str(pattern).strip():
        raise AppError("规则 pattern 不能为空")
    if kind == "header" and not field:
        raise AppError("header 规则需要 field 指定请求头名")
    if kind in ("path_regex", "user_agent", "header"):
        try:
            re.compile(str(pattern))
        except re.error as e:
            raise AppError(f"正则表达式无效：{e}")


def _rule_id(kind, pattern, field):
    src = f"{kind}|{pattern}|{field or ''}"
    return "r-" + hashlib.sha1(src.encode()).hexdigest()[:10]


# ---------- 规则 CRUD ----------

def get_config():
    """完整配置（含订阅信息），供 CLI/Web 展示。"""
    cfg = _load()
    subs = []
    for s in cfg.get("subscriptions", []):
        subs.append({
            "url": s.get("url"),
            "name": s.get("name") or s.get("url"),
            "enabled": bool(s.get("enabled", True)),
            "interval_sec": s.get("interval_sec", 3600),
            "last_fetch": s.get("last_fetch"),
            "last_error": s.get("last_error"),
            "rule_count": len(s.get("rules", [])),
        })
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "blacklist_ips": list(cfg.get("blacklist_ips", [])),
        "whitelist_ips": list(cfg.get("whitelist_ips", [])),
        "rules": list(cfg.get("rules", [])),
        "subscriptions": subs,
        "rate_limit": cfg.get("rate_limit", {"enabled": False, "requests": 60, "window": "10s"}),
    }


def render_config():
    """渲染给后端用的中性结构：仅含生效的本地规则 + 已启用订阅中的规则。"""
    cfg = _load()
    rules = []
    for r in cfg.get("rules", []):
        if r.get("enabled", True):
            rules.append({"kind": r["kind"], "pattern": r["pattern"],
                          "field": r.get("field"), "name": r.get("name", "")})
    for sub in cfg.get("subscriptions", []):
        if not sub.get("enabled", True):
            continue
        for r in sub.get("rules", []):
            rules.append({"kind": r["kind"], "pattern": r["pattern"],
                          "field": r.get("field"), "name": r.get("name", "")})
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "blacklist_ips": list(cfg.get("blacklist_ips", [])),
        "whitelist_ips": list(cfg.get("whitelist_ips", [])),
        "rules": rules,
        "rate_limit": cfg.get("rate_limit", {"enabled": False, "requests": 60, "window": "10s"}),
    }


def set_enabled(enabled):
    cfg = _load()
    cfg["enabled"] = bool(enabled)
    _save(cfg)
    return {"enabled": bool(enabled)}


def add_rule(kind, pattern, field=None, name=None):
    _validate_rule(kind, pattern, field)
    cfg = _load()
    rid = _rule_id(kind, pattern, field)
    rules = cfg.setdefault("rules", [])
    if any(r.get("id") == rid for r in rules):
        raise AppError(f"规则已存在（{kind} {field or ''} {pattern}）")
    rules.append({"id": rid, "kind": kind, "pattern": str(pattern),
                  "field": field or None, "name": name or "",
                  "enabled": True, "source": "local", "created": int(time.time())})
    _save(cfg)
    return get_config()


def remove_rule(rule_id):
    cfg = _load()
    rules = cfg.get("rules", [])
    before = len(rules)
    cfg["rules"] = [r for r in rules if r.get("id") != rule_id]
    if len(cfg["rules"]) == before:
        raise AppError(f"规则不存在：{rule_id}")
    _save(cfg)
    return get_config()


def set_rule_enabled(rule_id, enabled):
    cfg = _load()
    for r in cfg.get("rules", []):
        if r.get("id") == rule_id:
            r["enabled"] = bool(enabled)
            _save(cfg)
            return get_config()
    raise AppError(f"规则不存在：{rule_id}")


def add_ip(kind, ip):
    """kind: blacklist / whitelist"""
    if kind not in ("blacklist", "whitelist"):
        raise AppError("kind 只能是 blacklist 或 whitelist")
    ip = (ip or "").strip()
    if not _valid_ip(ip):
        raise AppError(f"IP/网段无效：{ip}")
    cfg = _load()
    lst = cfg.setdefault(f"{kind}_ips", [])
    if ip in lst:
        raise AppError(f"{ip} 已在{kind}名单中")
    lst.append(ip)
    _save(cfg)
    return get_config()


def remove_ip(kind, ip):
    if kind not in ("blacklist", "whitelist"):
        raise AppError("kind 只能是 blacklist 或 whitelist")
    ip = (ip or "").strip()
    cfg = _load()
    lst = cfg.setdefault(f"{kind}_ips", [])
    if ip not in lst:
        raise AppError(f"{ip} 不在{kind}名单中")
    lst.remove(ip)
    _save(cfg)
    return get_config()


def set_rate_limit(enabled, requests=None, window=None):
    cfg = _load()
    rl = cfg.setdefault("rate_limit", {"enabled": False, "requests": 60, "window": "10s"})
    if requests is not None:
        requests = int(requests)
        if not (1 <= requests <= 10 ** 7):
            raise AppError("请求数需在 1-10000000 之间")
        rl["requests"] = requests
    if window is not None:
        window = str(window).strip()
        if not _WINDOW_RE.fullmatch(window):
            raise AppError("时间窗口格式如 10s / 1m / 1h")
        rl["window"] = window
    rl["enabled"] = bool(enabled)
    _save(cfg)
    return get_config()


# ---------- 订阅 ----------

def _fetch_rules(url):
    """拉取远程规则。内容可为 {rules:[...]} 或规则数组。返回 (rules, skipped)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "aups-waf/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, dict):
        items = data.get("rules", data.get("data", []))
    elif isinstance(data, list):
        items = data
    else:
        raise AppError("订阅内容需为规则数组或 {\"rules\":[...]}")
    rules, skipped = [], 0
    for it in items:
        try:
            kind = str(it.get("kind", "")).strip()
            pattern = str(it.get("pattern", "")).strip()
            field = (str(it.get("field")).strip() if it.get("field") else None)
            _validate_rule(kind, pattern, field)
            rules.append({"id": _rule_id(kind, pattern, field), "kind": kind,
                          "pattern": pattern, "field": field,
                          "name": str(it.get("name", "")).strip(),
                          "enabled": True, "source": "subscribed"})
        except (AppError, AttributeError):
            skipped += 1
    return rules, skipped


RECOMMENDED_RULES_URL = ("https://raw.githubusercontent.com/upcyan/"
                         "AUPS/main/waf-rules.json")
RECOMMENDED_RULES_NAME = "OWASP CRS 精选（Lucky CorazaWAF 同源）"


def subscribe_recommended(interval_sec=3600):
    """一键加入内置推荐规则集订阅（OWASP CRS 精选，aups 兼容格式）并立即同步。"""
    try:
        interval_sec = max(60, int(interval_sec))
    except (TypeError, ValueError):
        raise AppError("订阅间隔需为秒数（至少 60）")
    result = subscribe_set(RECOMMENDED_RULES_URL, name=RECOMMENDED_RULES_NAME,
                           interval_sec=interval_sec)
    try:
        result["sync"] = subscribe_sync(RECOMMENDED_RULES_URL)
    except Exception as e:
        result["sync"] = {"error": str(e)}
    result["url"] = RECOMMENDED_RULES_URL
    return result


def subscribe_set(url, name=None, interval_sec=3600):
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise AppError("订阅地址需为 http(s):// URL")
    try:
        interval_sec = max(60, int(interval_sec))
    except (TypeError, ValueError):
        raise AppError("订阅间隔需为秒数（至少 60）")
    cfg = _load()
    subs = cfg.setdefault("subscriptions", [])
    for s in subs:
        if s["url"] == url:
            s["name"] = name or s.get("name") or url
            s["interval_sec"] = interval_sec
            s["enabled"] = True
            _save(cfg)
            return {"url": url, "updated": True}
    subs.append({"url": url, "name": name or url, "enabled": True,
                 "interval_sec": interval_sec, "last_fetch": None,
                 "last_error": None, "rules": []})
    _save(cfg)
    return {"url": url, "added": True}


def subscribe_remove(url):
    cfg = _load()
    subs = cfg.get("subscriptions", [])
    before = len(subs)
    cfg["subscriptions"] = [s for s in subs if s.get("url") != url]
    if len(cfg["subscriptions"]) == before:
        raise AppError(f"订阅不存在：{url}")
    _save(cfg)
    return {"url": url, "removed": True}


def subscribe_sync(url=None, due_only=False):
    """拉取订阅规则。url 为空时同步所有已启用订阅；due_only 时仅同步已到期的。

    due_only 供定时任务使用：按各订阅 interval_sec 判断是否到期。
    """
    cfg = _load()
    subs = cfg.get("subscriptions", [])
    if not subs:
        raise AppError("尚未配置任何订阅")
    if url and not any(s.get("url") == url for s in subs):
        raise AppError(f"订阅不存在：{url}")
    now = int(time.time())
    targets = []
    for s in subs:
        if url and s.get("url") != url:
            continue
        if not s.get("enabled", True):
            continue
        if due_only:
            last = s.get("last_fetch") or 0
            if now - last < int(s.get("interval_sec", 3600)):
                continue
        targets.append(s)
    if not targets:
        return {"synced": [], "note": ("暂无到期订阅" if due_only else "没有已启用的订阅")}
    result = []
    for s in targets:
        entry = {"url": s["url"], "ok": False, "rules": 0, "skipped": 0, "error": None}
        try:
            rules, skipped = _fetch_rules(s["url"])
            s["rules"] = rules
            s["last_fetch"] = now
            s["last_error"] = None
            entry.update(ok=True, rules=len(rules), skipped=skipped)
        except Exception as e:
            s["last_error"] = str(e)
            entry["error"] = str(e)
        result.append(entry)
    _save(cfg)
    return {"synced": result}
