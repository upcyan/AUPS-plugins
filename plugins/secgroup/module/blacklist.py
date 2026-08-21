"""安全组远程黑名单订阅。

兼容：
- CrowdSec Blocklist Mirror 的纯文本 IP/CIDR；
- CrowdSec LAPI Decisions JSON 的 value/scope；
- 长亭 SafeLine 黑名单规则 JSON 的 ip 数组；
- 通用 data/items/rules 嵌套 JSON。
"""

import base64
import hashlib
import ipaddress
import json
import os
import tempfile
import time
import urllib.request

from ... import config
from ...core.errors import AppError

CONFIG_FILE = os.path.join(config.PANEL_CONFIG_DIR, "secgroup", "blacklists.json")
CRON_FILE = "/etc/cron.d/aups-secgroup-blacklist"
MAX_DOWNLOAD = 16 * 1024 * 1024
MAX_NETWORKS = 250000
PROVIDERS = ("chaitin", "crowdsec", "generic")
AUTH_TYPES = ("none", "bearer", "x-api-key", "basic")


def _default():
    return {"subscriptions": []}


def _load():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else _default()
    except (OSError, ValueError):
        return _default()


def _save(data):
    directory = os.path.dirname(CONFIG_FILE)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".blacklists-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _sub_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _normalise(value):
    value = str(value or "").strip().strip("[](),;\"'")
    if not value:
        return None
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError:
        return None


def _json_candidates(value, parent=""):
    keys = {"ip", "ips", "cidr", "cidrs", "value", "values", "address", "addresses",
            "network", "networks", "blacklist", "blocklist"}
    if isinstance(value, dict):
        scope = str(value.get("scope", "")).lower()
        for key, item in value.items():
            if key.lower() in keys or key.lower() in ("data", "items", "rules", "decisions", "new"):
                yield from _json_candidates(item, key.lower())
            elif scope in ("ip", "range") and key.lower() == "value":
                yield from _json_candidates(item, key.lower())
    elif isinstance(value, list):
        for item in value:
            yield from _json_candidates(item, parent)
    elif isinstance(value, str) and parent in keys:
        yield value


def parse_payload(raw):
    """解析纯文本或 JSON，返回去重、折叠后的 IP/CIDR。"""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    candidates = []
    try:
        data = json.loads(text)
        candidates.extend(_json_candidates(data))
    except ValueError:
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            candidates.extend(part.strip() for part in line.replace(",", " ").split())
    networks = []
    for value in candidates:
        network = _normalise(value)
        if network:
            networks.append(ipaddress.ip_network(network))
        if len(networks) > MAX_NETWORKS:
            raise AppError(f"黑名单超过安全上限 {MAX_NETWORKS} 条")
    v4 = list(ipaddress.collapse_addresses(n for n in networks if n.version == 4))
    v6 = list(ipaddress.collapse_addresses(n for n in networks if n.version == 6))
    return [str(n) for n in v4 + v6]


def _fetch(sub):
    url = str(sub.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise AppError("订阅地址需为 http(s):// URL")
    headers = {"User-Agent": "aups-secgroup/1.1"}
    token = str(sub.get("token") or "")
    auth_type = sub.get("auth_type") or "none"
    if token and auth_type == "bearer":
        headers["Authorization"] = "Bearer " + token
    elif token and auth_type == "x-api-key":
        headers["X-Api-Key"] = token
    elif token and auth_type == "basic":
        headers["Authorization"] = "Basic " + base64.b64encode(token.encode()).decode()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise AppError("黑名单订阅内容超过 16 MiB 安全上限")
    return parse_payload(raw)


def _public(sub):
    return {
        "id": sub.get("id"), "name": sub.get("name"), "provider": sub.get("provider"),
        "url": sub.get("url"), "auth_type": sub.get("auth_type", "none"),
        "has_token": bool(sub.get("token")), "enabled": bool(sub.get("enabled", True)),
        "interval_sec": int(sub.get("interval_sec", 3600)),
        "last_fetch": sub.get("last_fetch"), "last_error": sub.get("last_error"),
        "count": len(sub.get("networks") or []),
    }


def schedule_status():
    if not os.path.isfile(CRON_FILE):
        return {"enabled": False, "check_minutes": 5, "path": CRON_FILE}
    try:
        text = open(CRON_FILE, encoding="utf-8").read()
    except OSError:
        return {"enabled": False, "check_minutes": 5, "path": CRON_FILE}
    marker = "AUPS_SECGROUP_CHECK_MINUTES="
    minutes = 5
    for line in text.splitlines():
        if marker in line:
            try:
                minutes = int(line.split(marker, 1)[1].strip())
            except ValueError:
                pass
    return {"enabled": True, "check_minutes": minutes, "path": CRON_FILE}


def set_schedule(enabled, check_minutes=5):
    if not enabled:
        try:
            os.remove(CRON_FILE)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise AppError(f"关闭定时同步失败：{exc}")
        return schedule_status()
    try:
        minutes = int(check_minutes)
    except (TypeError, ValueError):
        raise AppError("检查频率需为分钟数")
    if minutes not in (1, 5, 10, 15, 30, 60):
        raise AppError("检查频率仅支持 1/5/10/15/30/60 分钟")
    expr = f"*/{minutes} * * * *" if minutes < 60 else "0 * * * *"
    content = (f"# AUPS_SECGROUP_CHECK_MINUTES={minutes}\n{expr} root "
               "/usr/local/bin/aups plugins secgroup secgroup blacklist-sync --due "
               ">/dev/null 2>&1\n")
    try:
        with open(CRON_FILE, "w", encoding="utf-8") as file:
            file.write(content)
        os.chmod(CRON_FILE, 0o600)
    except OSError as exc:
        raise AppError(f"设置定时同步失败：{exc}")
    return schedule_status()


def status():
    data = _load()
    subs = [_public(s) for s in data.get("subscriptions", []) if isinstance(s, dict)]
    combined = _combined(data)
    return {"subscriptions": subs, "subscription_count": len(subs),
            "network_count": len(combined), "schedule": schedule_status()}


def set_subscription(url, name=None, provider="generic", auth_type=None, token=None,
                     interval_sec=3600, enabled=True, sync_now=False):
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise AppError("订阅地址需为 http(s):// URL")
    provider = str(provider or "generic").lower()
    if provider not in PROVIDERS:
        raise AppError("来源类型仅支持 chaitin / crowdsec / generic")
    default_auth = "x-api-key" if provider == "crowdsec" else ("bearer" if provider == "chaitin" else "none")
    auth_type = str(auth_type or default_auth).lower()
    if auth_type not in AUTH_TYPES:
        raise AppError("认证类型无效")
    try:
        interval_sec = max(60, int(interval_sec))
    except (TypeError, ValueError):
        raise AppError("更新周期至少 60 秒")
    data = _load()
    sub_id = _sub_id(url)
    current = next((s for s in data.setdefault("subscriptions", [])
                    if s.get("id") == sub_id), None)
    if current is None:
        current = {"id": sub_id, "url": url, "networks": [],
                   "last_fetch": None, "last_error": None}
        data["subscriptions"].append(current)
    current.update({"name": str(name or current.get("name") or url), "provider": provider,
                    "auth_type": auth_type, "enabled": bool(enabled),
                    "interval_sec": interval_sec})
    if auth_type == "none":
        current["token"] = ""
    elif token is not None:
        current["token"] = str(token)
    _save(data)
    if sync_now:
        return sync(sub_id=sub_id)
    return _public(current)


def remove_subscription(sub_id):
    data = _load()
    before = len(data.get("subscriptions", []))
    data["subscriptions"] = [s for s in data.get("subscriptions", [])
                             if s.get("id") != sub_id]
    if len(data["subscriptions"]) == before:
        raise AppError("黑名单订阅不存在")
    _save(data)
    apply_runtime(data)
    return {"id": sub_id, "removed": True}


def _combined(data=None):
    data = data or _load()
    networks = []
    for sub in data.get("subscriptions", []):
        if sub.get("enabled", True):
            networks.extend(sub.get("networks") or [])
    parsed = [ipaddress.ip_network(value) for n in networks
              for value in [_normalise(n)] if value]
    v4 = ipaddress.collapse_addresses(n for n in parsed if n.version == 4)
    v6 = ipaddress.collapse_addresses(n for n in parsed if n.version == 6)
    return [str(n) for n in list(v4) + list(v6)]


def apply_runtime(data=None):
    from . import firewall
    return firewall.sync_blacklist_networks(_combined(data))


def sync(sub_id=None, due_only=False):
    data = _load()
    now = int(time.time())
    targets = []
    for sub in data.get("subscriptions", []):
        if sub_id and sub.get("id") != sub_id:
            continue
        if not sub.get("enabled", True):
            continue
        if due_only and now - int(sub.get("last_fetch") or 0) < int(sub.get("interval_sec", 3600)):
            continue
        targets.append(sub)
    if sub_id and not any(s.get("id") == sub_id for s in data.get("subscriptions", [])):
        raise AppError("黑名单订阅不存在")
    results = []
    for sub in targets:
        item = {"id": sub.get("id"), "name": sub.get("name"), "ok": False,
                "count": 0, "error": None}
        try:
            networks = _fetch(sub)
            sub["networks"] = networks
            sub["last_fetch"] = now
            sub["last_error"] = None
            item.update(ok=True, count=len(networks))
        except BaseException as exc:
            sub["last_error"] = str(exc)
            item["error"] = str(exc)
        results.append(item)
    _save(data)
    runtime = apply_runtime(data)
    return {"synced": results, "runtime": runtime,
            "note": "暂无到期订阅" if due_only and not targets else None}


__all__ = ["parse_payload", "status", "set_subscription", "remove_subscription",
           "sync", "apply_runtime", "set_schedule", "schedule_status"]
