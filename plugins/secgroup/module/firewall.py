"""基于 nftables 的 AUPS 原生安全组 provider。

仅维护 ``inet aups_secgroup`` 专用表，不清空、不改写系统其它规则。第一版采用
默认放行 + 显式阻断模型：close_port 添加 drop 规则，open_port 删除同一规则。
这样安装/启用插件不会意外切断 SSH 或面板连接。
"""

import hashlib
import ipaddress
import json
import os
import re
import tempfile

from ... import config
from ...core.errors import AppError
from ...core.util import has_cmd, run, run_privileged

TABLE = "aups_secgroup"
CHAIN = "input"
COMMENT_PREFIX = "aups-secgroup:"
RULES_FILE = os.path.join(config.PANEL_CONFIG_DIR, "secgroup", "rules.json")
BLACKLIST4 = "blacklist4"
BLACKLIST6 = "blacklist6"


def _load_specs():
    try:
        with open(RULES_FILE, encoding="utf-8") as file:
            data = json.load(file)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_specs(specs):
    directory = os.path.dirname(RULES_FILE)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".rules-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(specs, file, ensure_ascii=False, indent=2)
        os.replace(tmp, RULES_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _normalise(port, protocol="tcp", source=None):
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise AppError("端口必须是 1-65535 的整数")
    if not 1 <= port <= 65535:
        raise AppError("端口必须在 1-65535 之间")
    protocol = str(protocol or "tcp").strip().lower()
    if protocol not in ("tcp", "udp"):
        raise AppError("协议仅支持 tcp / udp")
    try:
        source = str(ipaddress.ip_network(source or "0.0.0.0/0", strict=False))
    except ValueError:
        raise AppError("来源必须是合法 IP 或 CIDR 网段")
    return port, protocol, source


def _rule_id(port, protocol, source):
    raw = f"drop|{protocol}|{port}|{source}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _require_nft():
    if not has_cmd("nft"):
        raise AppError("未安装 nftables，请先安装 nftables 软件包")


def _ensure(pwd=None):
    _require_nft()
    table = run(["nft", "list", "table", "inet", TABLE], check=False)
    if table.returncode != 0:
        run_privileged(["nft", "add", "table", "inet", TABLE], check=True, pwd=pwd)
    chain = run(["nft", "list", "chain", "inet", TABLE, CHAIN], check=False)
    if chain.returncode != 0:
        run_privileged([
            "nft", "add", "chain", "inet", TABLE, CHAIN, "\\{",
            "type", "filter", "hook", "input", "priority", "-5", "\\;",
            "policy", "accept", "\\;", "\\}",
        ], check=True, pwd=pwd)


def _ensure_blacklist_sets(pwd=None):
    """建立 IPv4/IPv6 interval set 及来源阻断规则。"""
    _ensure(pwd)
    for name, addr_type in ((BLACKLIST4, "ipv4_addr"), (BLACKLIST6, "ipv6_addr")):
        current = run(["nft", "list", "set", "inet", TABLE, name], check=False)
        if current.returncode != 0:
            run_privileged([
                "nft", "add", "set", "inet", TABLE, name, "\\{",
                "type", addr_type, "\\;", "flags", "interval", "\\;", "\\}",
            ], check=True, pwd=pwd)
        if not _handles(name):
            family = "ip6" if name == BLACKLIST6 else "ip"
            run_privileged([
                "nft", "add", "rule", "inet", TABLE, CHAIN,
                family, "saddr", f"@{name}", "drop", "comment", COMMENT_PREFIX + name,
            ], check=True, pwd=pwd)


def _chain_text():
    if not has_cmd("nft"):
        return ""
    result = run(["nft", "-a", "list", "chain", "inet", TABLE, CHAIN], check=False)
    return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()


def _handles(rule_id):
    tag = COMMENT_PREFIX + rule_id
    handles = []
    for line in _chain_text().splitlines():
        if tag not in line:
            continue
        match = re.search(r"#\s*handle\s+(\d+)", line)
        if match:
            handles.append(int(match.group(1)))
    return handles


def rules():
    out = []
    for line in _chain_text().splitlines():
        tag = re.search(r'aups-secgroup:([0-9a-f]{16})', line)
        if not tag:
            continue
        protocol = "udp" if re.search(r"\budp\s+dport\b", line) else "tcp"
        port_match = re.search(r"\b(?:tcp|udp)\s+dport\s+(\d+)", line)
        source_match = re.search(r"\bip6?\s+saddr\s+([^\s]+)", line)
        out.append({
            "id": tag.group(1), "action": "关闭", "protocol": protocol,
            "port": int(port_match.group(1)) if port_match else None,
            "source": source_match.group(1) if source_match else "全部来源",
        })
    return out


def status():
    installed = has_cmd("nft")
    text = _chain_text() if installed else "未安装 nftables"
    result = {
        "kind": "nftables-native", "installed": installed,
        "active": bool(installed and f"table inet {TABLE}" in text),
        "mode": "默认放行 / 显式关闭", "persistent": True,
        "rules": rules() if installed else _load_specs(),
        "status": text or "AUPS 安全组链尚未创建；首次添加规则时自动创建",
    }
    try:
        from . import blacklist
        summary = blacklist.status()
        result.update({
            "blacklist_supported": True,
            "blacklist_count": summary.get("network_count", 0),
            "blacklist_subscriptions": summary.get("subscription_count", 0),
        })
    except BaseException:
        result["blacklist_supported"] = False
    return result


def sync_blacklist_networks(networks, pwd=None):
    """原子刷新 nftables 黑名单集合。networks 必须已完成 IP/CIDR 归一化。"""
    _ensure_blacklist_sets(pwd)
    ipv4 = [n for n in networks if ":" not in n]
    ipv6 = [n for n in networks if ":" in n]
    directory = os.path.dirname(RULES_FILE)
    os.makedirs(directory, exist_ok=True)
    fd, script = tempfile.mkstemp(prefix=".blacklist-", suffix=".nft", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(f"flush set inet {TABLE} {BLACKLIST4}\n")
            file.write(f"flush set inet {TABLE} {BLACKLIST6}\n")
            for name, items in ((BLACKLIST4, ipv4), (BLACKLIST6, ipv6)):
                for pos in range(0, len(items), 500):
                    values = ", ".join(items[pos:pos + 500])
                    file.write(f"add element inet {TABLE} {name} {{ {values} }}\n")
        os.chmod(script, 0o600)
        run_privileged(["nft", "-f", script], check=True, pwd=pwd)
    finally:
        try:
            os.unlink(script)
        except OSError:
            pass
    return {"ok": True, "ipv4": len(ipv4), "ipv6": len(ipv6),
            "total": len(networks)}


def _add_drop(port, protocol, source, pwd=None):
    rule_id = _rule_id(port, protocol, source)
    if _handles(rule_id):
        return rule_id, True
    args = ["nft", "add", "rule", "inet", TABLE, CHAIN]
    if source not in ("0.0.0.0/0", "::/0"):
        args += ["ip6" if ":" in source else "ip", "saddr", source]
    args += [protocol, "dport", str(port), "drop", "comment", COMMENT_PREFIX + rule_id]
    run_privileged(args, check=True, pwd=pwd)
    return rule_id, False


def close_port(port, protocol="tcp", source=None, pwd=None):
    """关闭来源到端口的访问：在专用链添加 drop 规则并持久化。"""
    port, protocol, source = _normalise(port, protocol, source)
    _ensure(pwd)
    rule_id, existing = _add_drop(port, protocol, source, pwd)
    specs = _load_specs()
    spec = {"action": "关闭", "port": port, "protocol": protocol, "source": source}
    if not any(_rule_id(s.get("port"), s.get("protocol"), s.get("source")) == rule_id
               for s in specs):
        specs.append(spec)
        _save_specs(specs)
    return {"port": port, "protocol": protocol, "source": source,
            "closed": True, "existing": existing, "rule_id": rule_id}


def open_port(port, protocol="tcp", source=None, pwd=None):
    """放行来源到端口：删除本插件管理的对应 drop 规则。"""
    port, protocol, source = _normalise(port, protocol, source)
    _ensure(pwd)
    rule_id = _rule_id(port, protocol, source)
    handles = _handles(rule_id)
    for handle in handles:
        run_privileged(["nft", "delete", "rule", "inet", TABLE, CHAIN,
                        "handle", str(handle)], check=True, pwd=pwd)
    specs = [s for s in _load_specs()
             if _rule_id(s.get("port"), s.get("protocol"), s.get("source")) != rule_id]
    _save_specs(specs)
    return {"port": port, "protocol": protocol, "source": source,
            "opened": True, "removed": len(handles), "rule_id": rule_id}


def start():
    _ensure()
    restored = 0
    for spec in _load_specs():
        try:
            port, protocol, source = _normalise(
                spec.get("port"), spec.get("protocol"), spec.get("source"))
            _, existing = _add_drop(port, protocol, source)
            if not existing:
                restored += 1
        except (AppError, OSError, ValueError):
            continue
    blacklist_count = 0
    try:
        from . import blacklist
        blacklist_count = blacklist.apply_runtime().get("total", 0)
    except BaseException:
        pass
    return {"ok": True, "restored": restored, "blacklist": blacklist_count}


def stop():
    if has_cmd("nft"):
        run_privileged(["nft", "delete", "table", "inet", TABLE], check=False)
    return {"ok": True}


remove = stop


__all__ = ["status", "rules", "open_port", "close_port", "sync_blacklist_networks",
           "start", "stop", "remove"]
