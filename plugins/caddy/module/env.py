"""caddy 环境业务逻辑（status / install / 配置路径）。

软件统一部署到 PANEL_HOME/runtime/caddy，配置在 PANEL_HOME/config/caddy，数据在 PANEL_HOME/data/caddy；
caddy 相关配置路径（Caddyfile/日志/WAF）随插件解耦到此处（原在核心 config）。
"""

import os
import shutil

from ... import config
from ... import pkg
from ...errors import AppError
from ...util import run

# caddy 配置路径（原在核心 config，随插件解耦）
CADDYFILE = os.environ.get("AUP_CADDYFILE", "/etc/caddy/Caddyfile")
CADDY_LOG_FILE = os.environ.get("AUP_CADDY_LOG", "/var/log/caddy/access.log")
WAF_FILE = os.path.join(config.CONF_DIR, "waf.json")


def caddy_binary():
    """面板部署的 caddy 二进制优先，否则系统 PATH 中的 caddy；无则 None。"""
    p = os.path.join(config.plugin_dir("caddy", "runtime"), "caddy")
    if os.path.isfile(p) and os.access(p, os.X_OK):
        return p
    return shutil.which("caddy")


def caddy_config_file():
    """面板部署的 Caddyfile 优先，否则系统 /etc/caddy/Caddyfile。"""
    p = os.path.join(config.plugin_dir("caddy", "config"), "Caddyfile")
    if os.path.isfile(p):
        return p
    return CADDYFILE


def status():
    d = config.plugin_paths("caddy")
    bin_path = caddy_binary()
    installed = bool(bin_path)
    ver = None
    if installed:
        r = run([bin_path, "version"])
        if r.returncode == 0:
            ver = (r.stdout or r.stderr or "").strip().splitlines()[0]
    deployed_bin = os.path.join(config.plugin_dir("caddy", "runtime"), "caddy")
    return {"name": "caddy", "installed": installed, "version": ver,
            "deployed": os.path.isfile(deployed_bin),
            "binary": bin_path, "config_file": caddy_config_file(),
            "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}


def install():
    """部署 caddy：优先复制系统 caddy 到面板目录，否则用包管理器安装。"""
    sys_bin = shutil.which("caddy")
    if not sys_bin:
        pkg.install(["caddy"])
        sys_bin = shutil.which("caddy")
    if not sys_bin:
        raise AppError("caddy 安装失败，未找到 caddy 命令")
    config.ensure_panel_dirs("caddy")
    runtime_bin = os.path.join(config.plugin_dir("caddy", "runtime"), "caddy")
    shutil.copy2(sys_bin, runtime_bin)
    os.chmod(runtime_bin, 0o755)
    # 迁移系统 Caddyfile 到面板配置目录（如存在且尚未迁移）
    dst_caddyfile = os.path.join(config.plugin_dir("caddy", "config"), "Caddyfile")
    if os.path.isfile(CADDYFILE) and not os.path.isfile(dst_caddyfile):
        shutil.copy2(CADDYFILE, dst_caddyfile)
    return {"ok": True, "source": "runtime", "message": "caddy 已部署到面板目录", **status()}
