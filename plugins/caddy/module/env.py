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

# 容器部署：容器名 / 镜像（caddy 官方镜像，配置目录挂载为 /etc/caddy）
CONTAINER_NAME = os.environ.get("AUP_CADDY_CONTAINER", "aups-caddy")
CADDY_IMAGE = os.environ.get("AUP_CADDY_IMAGE", "caddy:2")


def deploy_method():
    """当前部署方式：host（实机）/ container（容器）。默认 host。"""
    return config.get_plugin_deploy("caddy")


def container_runtime():
    """探测容器运行时（docker/podman 优先顺序）；无则 None。"""
    for b in ("docker", "podman"):
        if has_cmd(b):
            return b
    return None


def container_status():
    """caddy 容器部署状态：{supported, exists, running, runtime, name, image}。"""
    rt = container_runtime()
    if not rt:
        return {"supported": False, "exists": False, "running": False,
                "runtime": None, "name": CONTAINER_NAME, "image": CADDY_IMAGE}
    res = run([rt, "inspect", CONTAINER_NAME])
    if res.returncode != 0:
        return {"supported": True, "exists": False, "running": False,
                "runtime": rt, "name": CONTAINER_NAME, "image": CADDY_IMAGE}
    running = False
    try:
        import json as _json
        data = _json.loads(res.stdout or "[]")
        running = bool(data and data[0].get("State", {}).get("Running"))
    except ValueError:
        running = False
    return {"supported": True, "exists": True, "running": running,
            "runtime": rt, "name": CONTAINER_NAME, "image": CADDY_IMAGE}


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
    deploy = deploy_method()
    if deploy == "container":
        cs = container_status()
        return {"name": "caddy", "installed": cs["exists"], "version": None,
                "deployed": cs["exists"], "deploy": "container",
                "container": cs, "binary": None,
                "config_file": caddy_config_file(),
                "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}
    bin_path = caddy_binary()
    installed = bool(bin_path)
    ver = None
    if installed:
        r = run([bin_path, "version"])
        if r.returncode == 0:
            ver = (r.stdout or r.stderr or "").strip().splitlines()[0]
    deployed_bin = os.path.join(config.plugin_dir("caddy", "runtime"), "caddy")
    return {"name": "caddy", "installed": installed, "version": ver,
            "deployed": os.path.isfile(deployed_bin), "deploy": "host",
            "binary": bin_path, "config_file": caddy_config_file(),
            "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}


def install():
    """部署 caddy：容器方式（deploy=container）或实机方式（host）。"""
    if deploy_method() == "container":
        return _container_install()
    return _host_install()


def _host_install():
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


def _container_install():
    """容器部署：以 caddy 官方镜像运行容器，挂载面板配置/数据目录到容器。"""
    rt = container_runtime()
    if not rt:
        raise AppError("未检测到容器运行时（docker/podman），无法容器部署 caddy")
    config.ensure_panel_dirs("caddy")
    d = config.plugin_paths("caddy")
    # 确保配置目录存在 Caddyfile（容器入口需要）
    dst_caddyfile = os.path.join(d["config"], "Caddyfile")
    if os.path.isfile(CADDYFILE) and not os.path.isfile(dst_caddyfile):
        shutil.copy2(CADDYFILE, dst_caddyfile)
    if not os.path.isfile(dst_caddyfile):
        with open(dst_caddyfile, "w", encoding="utf-8") as f:
            f.write("{\n    admin off\n}\n")
    # 拉取镜像
    pull = run([rt, "pull", CADDY_IMAGE])
    if pull.returncode != 0:
        raise AppError(f"拉取镜像 {CADDY_IMAGE} 失败: {(pull.stderr or '').strip()}")
    # 移除旧容器后重建（配置目录挂载 /etc/caddy，数据目录挂载 /data）
    run([rt, "rm", "-f", CONTAINER_NAME], check=False)
    args = [rt, "run", "-d", "--name", CONTAINER_NAME,
            "--restart", "unless-stopped",
            "-v", f"{d['config']}:/etc/caddy:ro",
            "-v", f"{d['data']}:/data",
            CADDY_IMAGE]
    res = run(args)
    if res.returncode != 0:
        raise AppError(f"创建 caddy 容器失败: {(res.stderr or '').strip()}")
    return {"ok": True, "source": "container", "message": "caddy 已部署为容器", **status()}


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
    """卸载：容器方式删除容器；实机方式停止面板 caddy、删除部署的二进制并还原 systemd 单元。

    只清理部署的软件（容器/二进制/systemd），不删除 config/data 目录——数据保留与否
    由市场卸载时的 keep_data 决定（keep_data=False 时市场侧会删除 config/data）。
    """
    if deploy_method() == "container":
        rt = container_runtime()
        if rt:
            run([rt, "rm", "-f", CONTAINER_NAME], check=False)
        shutil.rmtree(config.plugin_dir("caddy", "runtime"), ignore_errors=True)
        return {"name": "caddy", "removed": True, "deploy": "container"}
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
    return {"name": "caddy", "removed": True, "deploy": "host"}


def stop():
    """停用插件：停止 caddy 服务（容器/ systemd / 二进制），保留配置/数据/二进制。"""
    if deploy_method() == "container":
        rt = container_runtime()
        if rt:
            run([rt, "stop", CONTAINER_NAME], check=False)
        return {"name": "caddy", "stopped": True, "deploy": "container"}
    if has_cmd("systemctl"):
        run(["systemctl", "stop", "caddy"], check=False)
        return {"name": "caddy", "stopped": True, "deploy": "host"}
    bin_path = caddy_binary()
    if bin_path:
        run([bin_path, "stop"], check=False)
    return {"name": "caddy", "stopped": True, "deploy": "host"}


def start():
    """重新启用插件：启动 caddy 服务（容器/ systemd / 二进制）。"""
    if deploy_method() == "container":
        rt = container_runtime()
        if rt:
            run([rt, "start", CONTAINER_NAME], check=False)
        return {"name": "caddy", "started": True, "deploy": "container"}
    if has_cmd("systemctl"):
        run(["systemctl", "start", "caddy"], check=False)
        return {"name": "caddy", "started": True, "deploy": "host"}
    bin_path = caddy_binary()
    if bin_path:
        run([bin_path, "run"], check=False)
    return {"name": "caddy", "started": True, "deploy": "host"}


def instance(action):
    """实例控制：stop / restart / reload Caddy 服务（兼容容器与实机部署）。

    action ∈ stop/restart/reload。容器方式经运行时管理；实机方式用 systemctl
    或 caddy 二进制（`caddy reload --config` / `caddy stop`）。
    """
    if action not in ("stop", "restart", "reload"):
        raise AppError("action 需为 stop/restart/reload")
    if deploy_method() == "container":
        rt = container_runtime()
        if not rt:
            raise AppError("未检测到容器运行时，无法控制 caddy 容器")
        cs = container_status()
        if action == "reload":
            if not cs["running"]:
                raise AppError("caddy 容器未运行，无法 reload")
            res = run([rt, "exec", CONTAINER_NAME, "caddy", "reload",
                       "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"])
        elif action == "stop":
            res = run([rt, "stop", CONTAINER_NAME])
        else:  # restart
            res = run([rt, "restart", CONTAINER_NAME])
        if res.returncode != 0:
            raise AppError(f"caddy {action} 失败: {(res.stderr or '').strip()}")
        return {"action": action, "deploy": "container", **container_status()}
    # 实机方式
    if has_cmd("systemctl"):
        res = run(["systemctl", action, "caddy"])
        if res.returncode != 0:
            raise AppError(f"systemctl {action} caddy 失败: {(res.stderr or '').strip()}")
        return {"action": action, "deploy": "host", "method": "systemctl"}
    bin_path = caddy_binary()
    if not bin_path:
        raise AppError("未找到 caddy 命令，无法控制实例")
    if action == "reload":
        res = run([bin_path, "reload", "--config", caddy_config_file()])
    elif action == "stop":
        res = run([bin_path, "stop"])
    else:  # restart: stop + run
        run([bin_path, "stop"], check=False)
        res = run([bin_path, "run"], check=False)
    if res.returncode != 0:
        raise AppError(f"caddy {action} 失败: {(res.stderr or '').strip()}")
    return {"action": action, "deploy": "host", "method": "binary"}
