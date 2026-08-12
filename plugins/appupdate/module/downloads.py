"""下载统计（appupdate 模块）。

解析 Caddy access log（JSON 日志）。因面板置于 Cloudflare 之后，
Caddy 记录的真实客户端 IP 是 Cloudflare 边缘 IP，需用请求头 CF-Connecting-IP
还原用户 IP（见 README 的 Caddy log 配置）。
"""

import json
import os
import time

from ... import config


def _download_ip(line):
    """从一行 Caddy JSON access log 中提取用于去重的真实客户端 IP。

    优先 CF-Connecting-IP 请求头（Cloudflare 透传），否则退回 remote_ip。
    返回 (ip, used_cf_header)。
    """
    udp = line.get("request") or {}
    headers = udp.get("headers") or {}
    cf = headers.get("CF-Connecting-IP") or headers.get("Cf-Connecting-Ip") or headers.get("cf-connecting-ip")
    if cf:
        return cf[0] if isinstance(cf, list) else cf, True
    return udp.get("client_ip") or udp.get("remote_ip"), False


def _is_apk_uri(line):
    """根据请求 URI 或重定向 Location 判断是否 APK 下载相关。"""
    udp = line.get("request") or {}
    uri = udp.get("uri", "")
    if ".apk" in uri:
        return True
    resp = line.get("resp_headers") or {}
    loc = resp.get("Location") or resp.get("location")
    if loc:
        val = loc[0] if isinstance(loc, list) else loc
        if ".apk" in val:
            return True
    return False


def downloads():
    """解析 Caddy access log，统计各应用下载次数与独立用户(IP)数。

    返回 {available, source, used_cf_header, apps: [{name, total, unique_ips}]}
    """
    log_path = config.CADDY_LOG_FILE
    available = os.path.isfile(log_path)
    apps = {}
    used_cf = False
    try:
        log_data = open(log_path, encoding="utf-8", errors="replace").read()
    except OSError:
        log_data = ""

    for ln in log_data.splitlines():
        try:
            obj = json.loads(ln)
        except ValueError:
            continue
        if obj.get("logger") != "http.log.access":
            continue
        if obj.get("status") not in (200, 302):
            continue
        if not _is_apk_uri(obj):
            continue
        ip, cf = _download_ip(obj)
        if cf:
            used_cf = True
        app = _app_of_uri((obj.get("request") or {}).get("uri", ""))
        if app is None:
            continue
        entry = apps.setdefault(app, {"name": app, "total": 0, "ips": set()})
        entry["total"] += 1
        if ip:
            entry["ips"].add(ip)

    return {
        "available": available,
        "source": log_path if available else "(access 日志未开启)",
        "used_cf_header": used_cf,
        "log_lines_ts": _last_lines_ts(log_data),
        "apps": [
            {"name": a["name"], "total": a["total"], "unique_ips": len(a["ips"])}
            for a in apps.values()
        ],
    }


def _app_of_uri(uri):
    """由 URI 猜测所属应用（URI 首段）。"""
    parts = uri.strip("/").split("/")
    return parts[0] if parts and parts[0] else None


def _last_lines_ts(log_data):
    ts = None
    for ln in log_data.splitlines():
        try:
            obj = json.loads(ln)
        except ValueError:
            continue
        if obj.get("ts"):
            ts = obj["ts"]
    return None if ts is None else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
