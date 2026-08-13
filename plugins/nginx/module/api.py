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
    """生成面板 nginx 配置：监听 127.0.0.1:8080，不占 80/443，pid/日志落在数据目录。"""
    data = config.plugin_dir("nginx", "data")
    runtime = config.plugin_dir("nginx", "runtime")
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
        "        listen 127.0.0.1:8080;\n"
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


def install():
    """部署 nginx 到面板目录：复制二进制 + mime.types、生成面板配置并启动，停用系统 nginx。"""
    config.ensure_panel_dirs("nginx")
    bin_path = _bin()
    if not (os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)):
        sys_bin = shutil.which("nginx")
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
    _write_config()
    _stop_system()
    _stop()
    _start()
    return {"ok": True, "source": "runtime", "message": "nginx 已部署到面板目录", **status()}


def remove():
    """卸载：停止并删除面板目录下的 nginx。"""
    _stop()
    for kind in ("runtime", "config", "data"):
        shutil.rmtree(config.plugin_dir("nginx", kind), ignore_errors=True)
    return {"name": "nginx", "removed": True}
