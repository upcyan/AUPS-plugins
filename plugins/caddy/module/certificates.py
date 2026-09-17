"""读取 Caddy 自动 HTTPS 保存的证书（仅读取，不暴露私钥）。"""

from __future__ import annotations

import math
import os
import ssl
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from ... import config
from . import env as ENV


def _roots():
    """返回当前部署方式及历史安装位置可能使用的证书目录。"""
    data = Path(config.plugin_dir("caddy", "data"))
    paths = [
        data / "caddy" / "certificates",             # 容器：/data/caddy/...
        data / "caddydata" / "caddy" / "certificates",  # 实机：XDG_DATA_HOME
        Path("/var/lib/caddy/.local/share/caddy/certificates"),
        Path("/root/.local/share/caddy/certificates"),
    ]
    seen = set()
    return [p for p in paths if not (str(p) in seen or seen.add(str(p)))]


def _name(parts):
    return ", ".join("=".join(item) for group in parts for item in group)


def _cert_info(path: Path):
    try:
        decoded = ssl._ssl._test_decode_cert(str(path))
    except Exception:
        return None
    try:
        expires = parsedate_to_datetime(decoded.get("notAfter", "")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
    issued = None
    try:
        issued = parsedate_to_datetime(decoded.get("notBefore", "")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    names = [value for kind, value in decoded.get("subjectAltName", []) if kind == "DNS"]
    if not names:
        names = [value for group in decoded.get("subject", []) for kind, value in group if kind == "commonName"]
    left = math.ceil((expires - datetime.now(timezone.utc)).total_seconds() / 86400)
    return {
        "domain": names[0] if names else path.stem,
        "domains": names,
        "issuer": _name(decoded.get("issuer", [])) or "未知",
        "serial": decoded.get("serialNumber", ""),
        "issued_at": issued.isoformat() if issued else None,
        "expires_at": expires.isoformat(),
        "remaining_days": left,
        "status": "expired" if left < 0 else "expiring" if left <= 14 else "valid",
    }


def list_certificates():
    """列出 Caddy 管理的证书；忽略没有对应私钥或无法解析的文件。"""
    found, seen = [], set()
    for root in _roots():
        try:
            if not root.is_dir():
                continue
            for cert in root.rglob("*.crt"):
                if len(cert.relative_to(root).parts) > 8:
                    continue
                key = cert.with_suffix(".key")
                if not key.is_file():
                    continue
                marker = str(cert.resolve())
                if marker in seen:
                    continue
                info = _cert_info(cert)
                if not info:
                    continue
                seen.add(marker)
                info["storage"] = str(root)
                found.append(info)
        except OSError:
            continue
    return sorted(found, key=lambda item: (item["remaining_days"], item["domain"]))


def status():
    certificates = list_certificates()
    return {
        "certificates": certificates,
        "count": len(certificates),
        "deploy": ENV.deploy_method(),
        "automatic_renewal": True,
    }
