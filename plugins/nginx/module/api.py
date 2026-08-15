"""nginx 业务逻辑（CLI / Web 共用）。

软件统一部署到 PANEL_HOME/runtime/nginx，配置在 PANEL_HOME/config/nginx，数据在 PANEL_HOME/data/nginx。
部署后不占用系统路径、默认不监听 80/443（只监听 127.0.0.1:8080）。
"""

import os
import shutil

from ... import config
from ... import pkg
from ...errors import AppError
from ...util import has_cmd, run


def _bin():
    return os.path.join(config.plugin_dir("nginx", "runtime"), "nginx")


def _cfg():
    return os.path.join(config.plugin_dir("nginx", "config"), "nginx.conf")


def _mime():
    return os.path.join(config.plugin_dir("nginx", "runtime"), "mime.types")


def _pid():
    return os.path.join(config.plugin_dir("nginx", "data"), "nginx.pid")


def _write_config():
    """生成面板 nginx 配置：监听 127.0.0.1:<port>（安装参数 port，默认 8080），不占 80/443。"""
    data = config.plugin_dir("nginx", "data")
    runtime = config.plugin_dir("nginx", "runtime")
    try:
        port = int(config.get_plugin_params("nginx").get("port") or 8080)
    except (TypeError, ValueError):
        port = 8080
    mime_line = f"    include {runtime}/mime.types;\n" if os.path.isfile(_mime()) else ""
    conf = (
        "worker_processes 1;\n"
        f"pid {_pid()};\n"
        f"error_log {data}/error.log;\n"
        "events { worker_connections 1024; }\n"
        "http {\n"
        + mime_line +
        "    default_type application/octet-stream;\n"
        f"    access_log {data}/access.log;\n"
        "    sendfile on;\n"
        "    keepalive_timeout 65;\n"
        "    server {\n"
        f"        listen 127.0.0.1:{port};\n"
        "        server_name _;\n"
        f"        root {data}/html;\n"
        "        index index.html;\n"
        "    }\n"
        "}\n"
    )
    cfg = _cfg()
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    os.makedirs(os.path.join(data, "html"), exist_ok=True)
    with open(cfg, "w") as f:
        f.write(conf)
    return cfg


def _start():
    run([_bin(), "-c", _cfg()], check=True)


def _stop():
    bin_path = _bin()
    cfg = _cfg()
    if os.path.isfile(bin_path) and os.path.isfile(cfg):
        run([bin_path, "-c", cfg, "-s", "stop"], check=False)


def _stop_system():
    """停用并关闭系统安装的 nginx 服务（避免占用 80/443）。"""
    if has_cmd("systemctl"):
        run(["systemctl", "stop", "nginx"], check=False)
        run(["systemctl", "disable", "nginx"], check=False)


def status():
    d = config.plugin_paths("nginx")
    bin_path = _bin()
    deployed = os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)
    running = os.path.isfile(_pid())
    ver = None
    if deployed:
        r = run([bin_path, "-v"])
        ver = (r.stderr or r.stdout or "").strip()
    return {"name": "nginx", "installed": deployed or has_cmd("nginx"),
            "deployed": deployed, "running": running, "version": ver,
            "binary": bin_path, "config_file": _cfg(),
            "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}


def _migrate_system_config():
    """把系统 /etc/nginx 配置迁移到面板配置目录，改写 pid/日志/include 路径，保留站点/root 内容。"""
    sys_conf = "/etc/nginx"
    if not os.path.isfile(os.path.join(sys_conf, "nginx.conf")):
        return False
    cfg_dir = config.plugin_dir("nginx", "config")
    data = config.plugin_dir("nginx", "data")
    for name in os.listdir(sys_conf):
        src = os.path.join(sys_conf, name)
        dst = os.path.join(cfg_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    # 改写关键路径（include/pid/log 指向面板目录，root 内容保持原样）
    for root, _dirs, files in os.walk(cfg_dir):
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                with open(fp) as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            new = (text.replace("/etc/nginx", cfg_dir)
                       .replace("/run/nginx.pid", os.path.join(data, "nginx.pid"))
                       .replace("/var/run/nginx.pid", os.path.join(data, "nginx.pid"))
                       .replace("/var/log/nginx", os.path.join(data, "log")))
            if new != text:
                with open(fp, "w") as f:
                    f.write(new)
    os.makedirs(os.path.join(data, "html"), exist_ok=True)
    return True


def install():
    """部署 nginx 到面板目录，并妥善处理系统已安装的 nginx。

    - 系统已装 nginx：复用其二进制、迁移其配置到面板目录、停用系统服务（释放 80/443）。
    - 未装：用包管理器安装后部署二进制 + 生成默认面板配置（监听 127.0.0.1:8080）。
    """
    config.ensure_panel_dirs("nginx")
    bin_path = _bin()
    sys_bin = shutil.which("nginx")
    had_system = bool(sys_bin)
    if not (os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)):
        if not sys_bin:
            pkg.install(["nginx"])
            sys_bin = shutil.which("nginx")
        if not sys_bin:
            raise AppError("nginx 安装失败，未找到 nginx 命令")
        shutil.copy2(sys_bin, bin_path)
        os.chmod(bin_path, 0o755)
        mime_src = "/etc/nginx/mime.types"
        if os.path.isfile(mime_src):
            shutil.copy2(mime_src, _mime())
    if had_system and _migrate_system_config():
        msg = "检测到系统 nginx，已复用其二进制、迁移配置到面板目录并停用系统服务"
        source = "system"
    else:
        _write_config()
        msg = "nginx 已部署到面板目录（默认配置，监听 127.0.0.1:8080）"
        source = "runtime"
    _stop_system()
    _stop()
    _start()
    return {"ok": True, "source": source, "message": msg, **status()}


def remove():
    """卸载：停止面板部署的 nginx，删除运行时二进制（保留 config/data，由市场 keep_data 决定）。"""
    _stop()
    shutil.rmtree(config.plugin_dir("nginx", "runtime"), ignore_errors=True)
    return {"name": "nginx", "removed": True}
