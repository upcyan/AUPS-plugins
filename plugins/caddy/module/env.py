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
_DEFAULT_CADDYFILE = "{\n    admin 127.0.0.1:2019\n}\n"


def deploy_method():
    """当前部署方式：host（实机）/ container（容器）。默认 host。"""
    return config.get_plugin_deploy("caddy")


def _container_runtimes():
    """返回可用容器运行时；控制实例时优先找到实际持有容器的运行时。"""
    return [runtime for runtime in ("docker", "podman") if has_cmd(runtime)]


def _container_inspect(runtime):
    return run([runtime, "inspect", CONTAINER_NAME])


def container_runtime(prefer_existing=True):
    """探测 docker/podman；已有容器时优先返回其所属运行时。"""
    runtimes = _container_runtimes()
    if prefer_existing:
        for runtime in runtimes:
            if _container_inspect(runtime).returncode == 0:
                return runtime
    return runtimes[0] if runtimes else None


def container_status():
    """caddy 容器部署状态，兼容 docker/podman 与运行时后装场景。"""
    rt = container_runtime()
    if not rt:
        return {"supported": False, "exists": False, "running": False,
                "runtime": None, "name": CONTAINER_NAME, "image": CADDY_IMAGE}
    res = _container_inspect(rt)
    if res.returncode != 0:
        return {"supported": True, "exists": False, "running": False,
                "runtime": rt, "name": CONTAINER_NAME, "image": CADDY_IMAGE}
    running = False
    image = CADDY_IMAGE
    network = None
    try:
        import json as _json
        data = _json.loads(res.stdout or "[]")
        info = data[0] if data else {}
        running = bool(info.get("State", {}).get("Running"))
        image = info.get("Config", {}).get("Image") or CADDY_IMAGE
        network = info.get("HostConfig", {}).get("NetworkMode")
    except ValueError:
        running = False
    version = None
    if running:
        ver = run([rt, "exec", CONTAINER_NAME, "caddy", "version"])
        if ver.returncode == 0 and (ver.stdout or ver.stderr).strip():
            version = (ver.stdout or ver.stderr).strip().splitlines()[0]
    return {"supported": True, "exists": True, "running": running,
            "runtime": rt, "name": CONTAINER_NAME, "image": image,
            "version": version, "network": network}


def access_log_file():
    """返回宿主机可读的 access 日志路径；Caddyfile 内路径保持兼容。"""
    if deploy_method() == "container":
        return os.path.join(config.plugin_dir("caddy", "data"), "logs",
                            os.path.basename(CADDY_LOG_FILE) or "access.log")
    return CADDY_LOG_FILE


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
        return {"name": "caddy", "installed": cs["exists"], "version": cs.get("version"),
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


def post_install():
    """市场安装后按用户选择自动部署实机二进制或 Caddy 容器。

    即使系统已有 caddy，也执行 _host_install() 保证二进制复制到面板 runtime 目录
    （systemd unit 指向 PANEL_HOME/runtime/caddy/caddy）。
    """
    if deploy_method() == "container":
        return _container_install()
    runtime_bin = os.path.join(config.plugin_dir("caddy", "runtime"), "caddy")
    if os.path.isfile(runtime_bin) and os.access(runtime_bin, os.X_OK):
        return {"skipped": True, "message": f"caddy 已部署: {runtime_bin}"}
    return install()


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
    # 确保配置目录存在 Caddyfile（systemd 启动需要）
    dst_caddyfile = os.path.join(config.plugin_dir("caddy", "config"), "Caddyfile")
    if not os.path.isfile(dst_caddyfile):
        if os.path.isfile(CADDYFILE):
            shutil.copy2(CADDYFILE, dst_caddyfile)
        else:
            os.makedirs(os.path.dirname(dst_caddyfile), exist_ok=True)
            with open(dst_caddyfile, "w", encoding="utf-8") as f:
                f.write(_DEFAULT_CADDYFILE)
    # 从容器切换回实机时清理旧实例，避免 host 网络下抢占 80/443。
    for runtime in _container_runtimes():
        run([runtime, "rm", "-f", CONTAINER_NAME], check=False)
    # 切换 systemd 单元，让运行中的 caddy 加载面板二进制+配置
    _switch_unit(runtime_bin, caddy_config_file())
    # 确保服务启动并开机自启
    if has_cmd("systemctl"):
        run(["systemctl", "daemon-reload"], check=False)
        run(["systemctl", "start", "caddy"], check=False)
        run(["systemctl", "enable", "caddy"], check=False)
    return {"ok": True, "source": "runtime", "message": "caddy 已部署到面板目录", **status()}


def _container_install():
    """容器部署：使用 host 网络保持公共反代数据中的 127.0.0.1 后端语义。"""
    rt = container_runtime()
    if not rt:
        raise AppError("未检测到容器运行时（docker/podman），无法容器部署 caddy")
    config.ensure_panel_dirs("caddy")
    d = config.plugin_paths("caddy")
    container_config = os.path.join(d["data"], "config")
    container_logs = os.path.join(d["data"], "logs")
    os.makedirs(container_config, exist_ok=True)
    os.makedirs(container_logs, exist_ok=True)
    os.makedirs(config.BASE_DIR, exist_ok=True)
    # 确保配置目录存在 Caddyfile（容器入口需要）
    dst_caddyfile = os.path.join(d["config"], "Caddyfile")
    if os.path.isfile(CADDYFILE) and not os.path.isfile(dst_caddyfile):
        shutil.copy2(CADDYFILE, dst_caddyfile)
    if not os.path.isfile(dst_caddyfile):
        with open(dst_caddyfile, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_CADDYFILE)
    # 拉取镜像
    pull = run([rt, "pull", CADDY_IMAGE])
    if pull.returncode != 0:
        raise AppError(f"拉取镜像 {CADDY_IMAGE} 失败: {(pull.stderr or '').strip()}")
    # host 网络让容器可继续反代宿主机 127.0.0.1:port，与核心公共 API 约定兼容。
    # 切换前停止实机实例，并清理任一运行时中的同名旧容器，避免端口冲突。
    host_was_active = False
    if has_cmd("systemctl"):
        active = run(["systemctl", "is-active", "caddy"])
        host_was_active = active.returncode == 0 and active.stdout.strip() == "active"
        if host_was_active:
            run(["systemctl", "stop", "caddy"], check=False)
    if not host_was_active:
        host_bin = caddy_binary()
        if host_bin:
            run([host_bin, "stop"], check=False)
    for runtime in _container_runtimes():
        run([runtime, "rm", "-f", CONTAINER_NAME], check=False)
    args = [rt, "run", "-d", "--name", CONTAINER_NAME,
            "--restart", "unless-stopped",
            "--network", "host",
            "-v", f"{d['config']}:/etc/caddy:ro",
            "-v", f"{d['data']}:/data",
            "-v", f"{container_config}:/config",
            "-v", f"{container_logs}:{os.path.dirname(CADDY_LOG_FILE) or '/var/log/caddy'}",
            "-v", f"{config.BASE_DIR}:{config.BASE_DIR}:ro",
            CADDY_IMAGE]
    res = run(args)
    if res.returncode != 0:
        if host_was_active:
            run(["systemctl", "start", "caddy"], check=False)
        raise AppError(f"创建 caddy 容器失败: {(res.stderr or '').strip()}")
    cs = container_status()
    if not cs.get("running"):
        log = run([rt, "logs", "--tail", "50", CONTAINER_NAME])
        run([rt, "rm", "-f", CONTAINER_NAME], check=False)
        if host_was_active:
            run(["systemctl", "start", "caddy"], check=False)
        raise AppError("caddy 容器启动失败: " + (log.stderr or log.stdout or "未知错误").strip())
    return {"ok": True, "source": "container", "message": "caddy 已部署为容器", **status()}


def _switch_unit(runtime_bin, panel_caddyfile):
    """把 caddy systemd 单元的 ExecStart/ExecReload 指向面板二进制+配置，并重启。

    这样运行中的 caddy 才真正加载面板目录的配置，reload（systemctl reload caddy）
    也随之作用于面板配置，避免「面板改面板配置、进程却读系统配置」的分裂。
    若系统无 caddy.service 单元文件，自动创建一个。
    """
    unit = next((u for u in _UNIT_FILES if os.path.isfile(u)), None)
    if not unit:
        # 无单元文件：创建一个指向面板目录的基本单元
        unit = _UNIT_FILES[0]
        data_dir = os.path.join(config.plugin_dir("caddy", "data"), "caddydata")
        os.makedirs(data_dir, exist_ok=True)
        try:
            os.makedirs(os.path.dirname(unit), exist_ok=True)
            with open(unit, "w") as f:
                f.write(f"""[Unit]
Description=Caddy web server (AUPS managed)
After=network.target

[Service]
Type=notify
Environment=HOME={data_dir}
Environment=XDG_DATA_HOME={data_dir}
Environment=XDG_CONFIG_HOME={data_dir}
ExecStart={runtime_bin} run --config {panel_caddyfile} --adapter caddyfile
ExecReload=/bin/kill -USR1 $MAINPID
Restart=on-failure
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
""")
        except OSError:
            return
    try:
        with open(unit) as f:
            content = f.read()
    except OSError:
        return
    sys_bin = shutil.which("caddy") or "/usr/bin/caddy"
    new = content.replace(sys_bin, runtime_bin).replace("/etc/caddy/Caddyfile", panel_caddyfile)
    # 注入 HOME/XDG 数据目录，保证证书/ACME 状态持久化
    data_dir = os.path.join(config.plugin_dir("caddy", "data"), "caddydata")
    if "XDG_DATA_HOME" not in new:
        os.makedirs(data_dir, exist_ok=True)
        env_lines = (f"Environment=HOME={data_dir}\n"
                     f"Environment=XDG_DATA_HOME={data_dir}\n"
                     f"Environment=XDG_CONFIG_HOME={data_dir}\n")
        if "[Service]\n" in new:
            new = new.replace("[Service]\n", "[Service]\n" + env_lines, 1)
        else:
            new += env_lines
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
        for runtime in _container_runtimes():
            run([runtime, "rm", "-f", CONTAINER_NAME], check=False)
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
        if not rt:
            raise AppError("未检测到容器运行时，无法停止 caddy 容器")
        res = run([rt, "stop", CONTAINER_NAME])
        if res.returncode != 0:
            raise AppError(f"停止 caddy 容器失败: {(res.stderr or '').strip()}")
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
        if not rt:
            raise AppError("未检测到容器运行时，无法启动 caddy 容器")
        res = run([rt, "start", CONTAINER_NAME])
        if res.returncode != 0:
            raise AppError(f"启动 caddy 容器失败: {(res.stderr or '').strip()}")
        return {"name": "caddy", "started": True, "deploy": "container"}
    if has_cmd("systemctl"):
        run(["systemctl", "start", "caddy"], check=False)
        return {"name": "caddy", "started": True, "deploy": "host"}
    bin_path = caddy_binary()
    if bin_path:
        run([bin_path, "run"], check=False)
    return {"name": "caddy", "started": True, "deploy": "host"}


def logs(lines=100):
    """读取当前部署实例日志，API 对实机与容器保持同一返回结构。"""
    lines = max(1, min(int(lines or 100), 500))
    if deploy_method() == "container":
        rt = container_runtime()
        if not rt:
            return {"lines": [], "error": "未检测到容器运行时", "deploy": "container"}
        res = run([rt, "logs", "--tail", str(lines), CONTAINER_NAME])
        raw = "\n".join(part for part in ((res.stdout or "").strip(),
                                            (res.stderr or "").strip()) if part)
        if res.returncode != 0:
            return {"lines": [], "error": raw or "无法读取 caddy 容器日志",
                    "deploy": "container"}
        return {"lines": raw.splitlines()[-lines:], "error": None, "deploy": "container"}
    if not has_cmd("journalctl"):
        return {"lines": [], "error": "journalctl 不可用", "deploy": "host"}
    res = run(["journalctl", "-u", "caddy", "-n", str(lines),
               "--no-pager", "--output=short-iso"])
    raw = res.stdout.strip()
    error = (res.stderr or "").strip() if res.returncode != 0 and not raw else None
    return {"lines": raw.splitlines()[-lines:], "error": error, "deploy": "host"}


def instance(action):
    """实例控制：stop / restart / reload Caddy 服务（兼容容器与实机部署）。"""
    print(f"[caddy] instance(action={action!r})")
    if action not in ("stop", "restart", "reload", "start"):
        raise AppError("action 需为 stop/restart/reload/start")
    if deploy_method() == "container":
        rt = container_runtime()
        if not rt:
            raise AppError("未检测到容器运行时，无法控制 caddy 容器")
        cs = container_status()
        if action == "reload":
            if not cs["running"]:
                raise AppError("caddy 容器未运行，无法 reload")
            valid = run([rt, "exec", CONTAINER_NAME, "caddy", "validate",
                         "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"])
            if valid.returncode != 0:
                raise AppError(f"Caddyfile 校验失败: {(valid.stderr or valid.stdout).strip()}")
            res = run([rt, "exec", CONTAINER_NAME, "caddy", "reload",
                       "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"])
            # 兼容旧配置中的 admin off：校验通过后以重启容器应用新配置。
            if res.returncode != 0:
                res = run([rt, "restart", CONTAINER_NAME])
        elif action == "stop":
            res = run([rt, "stop", CONTAINER_NAME])
        elif action == "start":
            res = run([rt, "start", CONTAINER_NAME])
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
