"""反向代理抽象层。

aups 目前使用 Caddy 生成下载路由并注入 WAF 规则。后续如需更换为 nginx/haproxy 等，
只需在 BACKENDS 中注册新后端模块、并在 /etc/aups/rproxy.json 或环境变量
AUP_RPROXY_BACKEND 切换 backend，上层 cli/web 代码无需改动。

后端模块需实现：
  status()     -> dict  （反代自身状态）
  show()       -> dict  （当前配置文件 + 托管片段）
  preview()    -> dict  （将写入的托管片段，不改文件）
  apply()      -> dict  （写入托管片段并 reload）
  reload()     -> dict
"""

import json
import os

from .... import config
from ....errors import AppError

BACKENDS = {
    "caddy": "aups.modules.caddy.rproxy.caddy",
}


def _cfg():
    try:
        with open(config.RPROXY_FILE) as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("backend"):
            return d
    except (OSError, ValueError):
        pass
    return {"backend": os.environ.get("AUP_RPROXY_BACKEND", "caddy")}


def backend_name():
    return _cfg()["backend"]


def backend_list():
    return {"backend": backend_name(), "available": sorted(BACKENDS)}


def set_backend(name):
    if name not in BACKENDS:
        raise AppError(f"未知反代后端：{name}（可选：{'、'.join(sorted(BACKENDS))}）")
    os.makedirs(config.CONF_DIR, exist_ok=True)
    with open(config.RPROXY_FILE, "w") as f:
        json.dump({"backend": name}, f, ensure_ascii=False, indent=2)
    return {"backend": name}


def _backend():
    name = backend_name()
    modpath = BACKENDS.get(name)
    if not modpath:
        raise AppError(f"反代后端未实现：{name}")
    from importlib import import_module
    return import_module(modpath)


def status():
    b = _backend()
    return {"backend": backend_name(), **(b.status() or {})}


def show():
    return _backend().show()


def preview():
    return _backend().preview()


def apply(reload=True):
    return _backend().apply(reload=reload)


def reload():
    return _backend().reload()


def access_log_status():
    """Caddy access 日志配置状态。"""
    return _backend().access_log_status()


def enable_access_log():
    """开启 Caddy access 日志（写 Caddyfile 全局 log 并 reload）。"""
    return _backend().enable_access_log()
