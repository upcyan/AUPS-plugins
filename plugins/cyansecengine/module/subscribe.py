"""cyansecengine 在线规则订阅：拉取远程 YARA 规则库并定时同步。

默认订阅源：Neo23x0/signature-base（社区维护的 YARA 规则集，含 webshell/
挖矿/已知恶意样本特征），GitHub raw 直接可拉取，格式为纯 .yar 文件。

订阅列表存 data/cyansecengine/subscribe.json：
    [{"name", "url", "type": "yara", "interval_sec", "last_sync", "rule_count", "enabled"}]
同步时下载到 data/cyansecengine/rules/，供 scanner._scan_yara 加载。
"""

import datetime
import json
import os
import time
import urllib.request

from ... import config
from ...errors import AppError

DATA_DIR = os.path.join(config.PANEL_DATA_DIR, "cyansecengine")
RULES_DIR = os.path.join(DATA_DIR, "rules")
CONF_FILE = os.path.join(DATA_DIR, "subscribe.json")

# 默认推荐订阅（signature-base 精选 .yar 文件，GitHub raw 直接可拉）
# 这些路径随上游仓库变动，插件内置为"推荐"，可被用户删除或追加自己的源。
DEFAULT_SUBSCRIPTIONS = [
    {"name": "signature-base: CN webshells",
     "url": "https://raw.githubusercontent.com/Neo23x0/signature-base/master/yara/gen_cn_webshells.yar",
     "type": "yara", "interval_sec": 86400},
    {"name": "signature-base: pentest webshells",
     "url": "https://raw.githubusercontent.com/Neo23x0/signature-base/master/yara/cn_pentestset_webshells.yar",
     "type": "yara", "interval_sec": 86400},
    {"name": "signature-base: China Chopper",
     "url": "https://raw.githubusercontent.com/Neo23x0/signature-base/master/yara/apt_webshell_chinachopper.yar",
     "type": "yara", "interval_sec": 86400},
    {"name": "signature-base: webshells (laudanum)",
     "url": "https://raw.githubusercontent.com/Neo23x0/signature-base/master/yara/apt_laudanum_webshells.yar",
     "type": "yara", "interval_sec": 86400},
]


def _ensure():
    os.makedirs(RULES_DIR, exist_ok=True)


def _load():
    _ensure()
    try:
        with open(CONF_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, list):
            return d
    except (OSError, ValueError):
        pass
    return []


def _save(subs):
    _ensure()
    with open(CONF_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def _safe_rule_name(url):
    """由 URL 生成本地规则文件名（sanitize，防路径穿越）。"""
    base = url.rstrip("/").rsplit("/", 1)[-1] or "rule"
    base = "".join(c for c in base if c.isalnum() or c in "._-")
    return base or "rule.yar"


def list_subs():
    """返回订阅列表（含默认推荐的合并状态）。"""
    subs = _load()
    have = {s["url"] for s in subs}
    for d in DEFAULT_SUBSCRIPTIONS:
        if d["url"] not in have:
            subs.append({**d, "enabled": True, "last_sync": 0, "rule_count": 0})
    return subs


def add_sub(url, name=None, interval_sec=86400):
    """添加订阅。返回添加/更新后的列表。"""
    url = (url or "").strip()
    if not url.startswith("http"):
        raise AppError("订阅地址需为 http(s) 链接")
    subs = _load()
    for s in subs:
        if s["url"] == url:
            s["name"] = name or s.get("name", url)
            s["interval_sec"] = int(interval_sec or s.get("interval_sec", 86400))
            s["enabled"] = True
            _save(subs)
            return s
    sub = {"name": name or url, "url": url, "type": "yara",
           "interval_sec": int(interval_sec or 86400),
           "enabled": True, "last_sync": 0, "rule_count": 0}
    subs.append(sub)
    _save(subs)
    return sub


def remove_sub(url):
    """删除订阅并移除已下载的规则文件。"""
    subs = _load()
    subs = [s for s in subs if s["url"] != url]
    _save(subs)
    fn = _safe_rule_name(url)
    for suffix in (".yar", ".yara"):
        p = os.path.join(RULES_DIR, fn + suffix)
        if os.path.isfile(p):
            os.remove(p)
    return {"removed": True, "url": url}


def sync(url=None, due_only=False):
    """同步订阅规则到本地。url 指定则只同步该源；None 同步全部；due_only 仅到期者。"""
    _ensure()
    subs = list_subs()  # 含默认推荐（尚未持久化的也纳入）
    _save(subs)         # 先持久化，确保下次状态一致
    synced = []
    for s in subs:
        if not s.get("enabled"):
            continue
        if url and s["url"] != url:
            continue
        if due_only and s.get("interval_sec") and time.time() - s.get("last_sync", 0) < s["interval_sec"]:
            continue
        try:
            _fetch_rule(s)
            synced.append({"url": s["url"], "ok": True, "rule_count": s.get("rule_count", 0)})
        except AppError as e:
            synced.append({"url": s["url"], "ok": False, "error": str(e)})
    return {"synced": synced}


def _fetch_rule(sub):
    """下载单个订阅的规则文件到 rules/ 目录。"""
    req = urllib.request.Request(sub["url"], headers={"User-Agent": "aups-cyansec/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            blob = resp.read()
    except Exception as e:
        raise AppError(f"下载失败：{e}")
    if not blob:
        raise AppError("下载内容为空")
    fn = _safe_rule_name(sub["url"])
    path = os.path.join(RULES_DIR, fn)
    # 移除已存在的同名其它扩展名文件，统一用当前规则扩展名
    for old in (path + ".yara", path + ".yar"):
        if old != path and os.path.isfile(old):
            os.remove(old)
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(blob.decode("utf-8", errors="replace"))
    sub["rule_count"] = blob.count(b"rule ")
    sub["last_sync"] = time.time()
    _save(_load())
