"""caddy 环境业务逻辑（status / install / 配置路径）。

软件统一部署到 PANEL_HOME/runtime/caddy，配置在 PANEL_HOME/config/caddy，数据在 PANEL_HOME/data/caddy；
caddy 相关配置路径（Caddyfile/日志/WAF）随插件解耦到此处（原在核心 config）。
"""

import os
import shutil

from ... import config
from ... import pkg
from ...errors import AppError
from ...util import has_cmd, run

# caddy 配置路径（原在核心 config，随插件解耦）
CADDYFILE = os.environ.get("AUP_CADDYFILE", "/etc/caddy/Caddyfile")
CADDY_LOG_FILE = os.environ.get("AUP_CADDY_LOG", "/var/log/caddy/access.log")
WAF_FILE = os.path.join(config.CONF_DIR, "waf.json")

_UNIT_FILES = ("/etc/systemd/system/caddy.service", "/lib/systemd/system/caddy.service")


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
    """部署 caddy：复制系统 caddy 到面板目录、迁移配置，并让运行中的 caddy 使用面板二进制+配置。

    systemd 仅作为进程管理器（与面板自身 aups-web.service 一样），
    真正决定二进制/配置位置的是本函数写入的 systemd 单元路径。
    """
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
    # 切换 systemd 单元，让运行中的 caddy 加载面板二进制+配置
    _switch_unit(runtime_bin, caddy_config_file())
    return {"ok": True, "source": "runtime", "message": "caddy 已部署到面板目录", **status()}


def _switch_unit(runtime_bin, panel_caddyfile):
    """把 caddy systemd 单元的 ExecStart/ExecReload 指向面板二进制+配置，并重启。

    这样运行中的 caddy 才真正加载面板目录的配置，reload（systemctl reload caddy）
    也随之作用于面板配置，避免「面板改面板配置、进程却读系统配置」的分裂。
    """
    unit = next((u for u in _UNIT_FILES if os.path.isfile(u)), None)
    if not unit:
        return
    try:
        with open(unit) as f:
            content = f.read()
    except OSError:
        return
    sys_bin = shutil.which("caddy") or "/usr/bin/caddy"
    new = content.replace(sys_bin, runtime_bin).replace("/etc/caddy/Caddyfile", panel_caddyfile)
    if new == content:
        return
    # 备份原单元，供 remove() 还原
    try:
        with open(unit + ".aups-bak", "w") as f:
            f.write(content)
    except OSError:
        pass
    with open(unit, "w") as f:
        f.write(new)
    if has_cmd("systemctl"):
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "restart", "caddy"])


def remove():
    """卸载：停止面板 caddy、删除面板部署的二进制，并还原 systemd 单元为系统 caddy。

    只清理部署的软件（二进制/systemd），不删除 config/data 目录——数据保留与否
    由市场卸载时的 keep_data 决定（keep_data=False 时市场侧会删除 config/data）。
    """
    # 停止面板 caddy（若在运行）
    bin_path = caddy_binary()
    if bin_path:
        run([bin_path, "stop"], check=False)
    # 还原 systemd 单元（若曾切换）
    unit = next((u for u in _UNIT_FILES if os.path.isfile(u + ".aups-bak")), None)
    if unit:
        try:
            with open(unit + ".aups-bak") as f:
                orig = f.read()
            with open(unit, "w") as f:
                f.write(orig)
            os.remove(unit + ".aups-bak")
            if has_cmd("systemctl"):
                run(["systemctl", "daemon-reload"])
                run(["systemctl", "restart", "caddy"], check=False)
        except OSError:
            pass
    # 仅删除面板部署的二进制（runtime 目录），保留 config/data
    shutil.rmtree(config.plugin_dir("caddy", "runtime"), ignore_errors=True)
    return {"name": "caddy", "removed": True}
