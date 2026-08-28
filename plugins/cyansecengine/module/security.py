"""青·擎统一安全状态与检查编排。"""

from importlib import import_module

from ... import registry
from ...core import hostsec, rtguard, waf
from ...core import config


def _provider_module(capability, module):
    for name in registry.capability_providers(capability):
        try:
            return name, import_module(config.module_ref(f"modules.{name}.{module}"))
        except BaseException:
            continue
    return None, None


def _safe(call, default):
    try:
        return call()
    except BaseException as exc:
        return {"installed": False, "error": str(exc)} if default is None else default


def status():
    vuln_name, vuln = _provider_module("vuln", "scanner")
    firewall_name, firewall = _provider_module("firewall", "firewall")
    return {
        "plugin": "cyansecengine",
        "title": "青·擎",
        "firewall": {"provider": firewall_name,
                      "status": _safe(firewall.status, {}) if firewall else {"installed": False}},
        "waf": _safe(waf.get_config, {}),
        "vulnerability": {"provider": vuln_name,
                           "status": _safe(vuln.status, {}) if vuln else {"installed": False}},
        "hostsec": _safe(hostsec.status, {}),
        "realtime": _safe(rtguard.rt_status, {}),
    }


def check():
    """执行可用的漏洞检查，扫描器由各自插件实现。"""
    result = {"ok": True, "vulnerability": None, "engines": []}
    vuln_name, vuln = _provider_module("vuln", "scanner")
    if vuln and hasattr(vuln, "check"):
        result["vulnerability"] = vuln.check()
        result["engines"].append(vuln_name)
    for tool in ("rkhunter", "lmd", "yara"):
        for name in registry.tool_providers(tool):
            try:
                scanner = import_module(config.module_ref(f"modules.{name}.scanner"))
                if hasattr(scanner, "status"):
                    result["engines"].append(name)
            except BaseException:
                continue
    if result["vulnerability"]:
        result["ok"] = not bool(result["vulnerability"].get("fail"))
    return result


def waf_update(body):
    """统一 WAF 开关与限流入口，规则数据仍由核心 WAF 存储。"""
    body = body or {}
    result = {}
    if "enabled" in body:
        result["enabled"] = waf.set_enabled(bool(body["enabled"]))
    if "rate_limit" in body:
        rate = body.get("rate_limit") or {}
        result["rate_limit"] = waf.set_rate_limit(
            bool(rate.get("enabled", False)), rate.get("requests", 60),
            rate.get("window", "10s"))
    return result or waf.get_config()


def realtime_update(body):
    """统一实时防护入口，复用核心 daemon 生命周期和安全校验。"""
    body = body or {}
    return rtguard.set_rt(
        bool(body.get("enabled", False)), body.get("paths"),
        body.get("quarantine"), body.get("waf_block"), body.get("interval"))


__all__ = ["status", "check", "waf_update", "realtime_update"]
