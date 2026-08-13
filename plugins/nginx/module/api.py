"""nginx 业务逻辑（CLI / Web 共用）。

软件统一部署到 PANEL_HOME/runtime/nginx，配置在 PANEL_HOME/config/nginx，数据在 PANEL_HOME/data/nginx。
"""

from ... import config
from ...errors import AppError
from ...util import has_cmd, run


def status():
    d = config.plugin_paths("nginx")
    ver = None
    if has_cmd("nginx"):
        r = run(["nginx", "-v"])
        ver = (r.stderr or r.stdout or "").strip()
    return {"name": "nginx", "installed": has_cmd("nginx"), "version": ver,
            "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}


def install():
    """部署 nginx：优先复用系统 nginx，否则尝试包管理器安装。"""
    if has_cmd("nginx"):
        return {"ok": True, "source": "system", "message": "已检测到系统 nginx，直接使用",
                **status()}
    config.ensure_panel_dirs("nginx")
    if has_cmd("apt-get"):
        run(["apt-get", "install", "-y", "nginx"], check=True)
    elif has_cmd("dnf"):
        run(["dnf", "install", "-y", "nginx"], check=True)
    else:
        raise AppError("未找到包管理器（apt-get/dnf），请手动安装 nginx 并确保其在 PATH 中，"
                       "或将二进制部署到 " + config.plugin_dir("nginx", "runtime"))
    if not has_cmd("nginx"):
        raise AppError("nginx 安装后仍未检测到，请检查安装日志")
    return {"ok": True, "source": "pkg", "message": "已通过包管理器安装 nginx", **status()}
