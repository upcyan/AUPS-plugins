"""nginx 业务逻辑（CLI / Web 共用）。

软件统一部署到 PANEL_HOME/runtime/nginx，配置在 PANEL_HOME/config/nginx，数据在 PANEL_HOME/data/nginx。
部署后不占用系统路径、默认不监听 80/443（只监听 127.0.0.1:8080）。
"""

import os
import shutil
import json
import re
import tempfile

from ... import config
from ... import pkg
from ...errors import AppError
from ...util import has_cmd, run
from ...core import waf

IMAGE="nginx:1.27-alpine"
CONTAINER="aups-nginx"


def _params(): return config.get_plugin_params("nginx") or {}
def _method(): return _params().get("deploy_method") or "host"
def _runtime():
    chosen=_params().get("container_runtime")
    if chosen in ("docker","podman") and has_cmd(chosen): return chosen
    for name in ("docker","podman"):
        if has_cmd(name): return name
    raise AppError("需要 Docker 或 Podman")
def deploy_info(): return {"method":_method(),"runtime":(_runtime() if _method()=="container" else None),"config_shared":True,"data_shared":True}


def _bin():
    return os.path.join(config.plugin_dir("nginx", "runtime"), "nginx")


def _cfg():
    return os.path.join(config.plugin_dir("nginx", "config"), "nginx.conf")


def _mime():
    return os.path.join(config.plugin_dir("nginx", "runtime"), "mime.types")


def _pid():
    return os.path.join(config.plugin_dir("nginx", "data"), "nginx.pid")


def _sites_state(): return os.path.join(config.plugin_dir("nginx", "config"), "sites.json")
def _sites_conf(): return os.path.join(config.plugin_dir("nginx", "config"), "aups-sites.conf")


def _load_sites():
    try:
        with open(_sites_state(), encoding="utf-8") as f: data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError): return []


def _domain(host):
    host = (host or "").strip().lower()
    if not re.fullmatch(r"(?:\*\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host): raise AppError("站点域名格式无效")
    return host


def _render_sites(sites):
    wc = waf.render_config()
    out = ["# AUPS managed sites"]
    if wc.get("enabled") and (wc.get("rate_limit") or {}).get("enabled"):
        rl=wc["rate_limit"]; window=str(rl.get("window","10s")); requests=max(1,int(rl.get("requests",60)))
        seconds=max(1, int(window[:-1]) * ({"m":60,"h":3600,"d":86400}.get(window[-1],1))) if window[-1].isalpha() else max(1,int(window))
        out.append(f"limit_req_zone $binary_remote_addr zone=aups_waf:10m rate={max(1,requests//seconds)}r/s;")
    for s in sites:
        o=s.get("options") or {}; tls=o.get("tls") or {}; upstreams=o.get("upstreams") or []
        if upstreams:
            name="aups_"+re.sub(r"[^a-z0-9]","_",s["host"])
            out.append(f"upstream {name} {{")
            for u in upstreams:
                target=u.get("target",""); weight=max(1,int(u.get("weight",1)))
                if target: out.append(f"    server {target} weight={weight} max_fails={max(1,int(u.get('max_fails',3)))} fail_timeout={int(u.get('fail_timeout',10))}s;")
            out.append("}"); target=name
        else: target=s.get("target","")
        listen="443 ssl" if tls.get("cert") and tls.get("key") else "80"
        out.extend(["server {",f"    listen {listen};",f"    server_name {s['host']};"])
        if wc.get("enabled"):
            for ip in wc.get("whitelist_ips") or []: out.append(f"    allow {ip};")
            if wc.get("whitelist_ips"): out.append("    deny all;")
            else:
                for ip in wc.get("blacklist_ips") or []: out.append(f"    deny {ip};")
            if (wc.get("rate_limit") or {}).get("enabled"): out.append("    limit_req zone=aups_waf burst=20 nodelay;")
            for rule in wc.get("rules") or []:
                kind,pattern,field=rule.get("kind"),str(rule.get("pattern","")).replace('"','\\"'),rule.get("field")
                if kind=="user_agent": out.append(f'    if ($http_user_agent ~* "{pattern}") {{ return 403; }}')
                elif kind=="method": out.append(f'    if ($request_method ~* "{pattern}") {{ return 403; }}')
                elif kind=="path_regex": out.append(f'    if ($request_uri ~* "{pattern}") {{ return 403; }}')
                elif kind=="query" and field and re.fullmatch(r"[A-Za-z0-9_]+",field): out.append(f'    if ($arg_{field} ~* "{pattern}") {{ return 403; }}')
                elif kind=="header" and field and re.fullmatch(r"[A-Za-z0-9-]+",field): out.append(f'    if ($http_{field.lower().replace("-","_")} ~* "{pattern}") {{ return 403; }}')
        if "ssl" in listen: out.extend([f"    ssl_certificate {tls['cert']};",f"    ssl_certificate_key {tls['key']};"])
        if s.get("mode")=="file_server":
            out.extend([f"    root {target};","    index index.html;"])
            if o.get("download_routes"): out.append(f"    include {_routes_conf()};")
        else:
            out.extend(["    location / {",f"        proxy_pass http://{target};","        proxy_set_header Host $host;","        proxy_set_header X-Real-IP $remote_addr;","        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;","        proxy_set_header X-Forwarded-Proto $scheme;"])
            if o.get("websocket",True): out.extend(["        proxy_http_version 1.1;","        proxy_set_header Upgrade $http_upgrade;","        proxy_set_header Connection \"upgrade\";"])
            out.append("    }")
        for line in (s.get("extra") or "").splitlines():
            if line.strip(): out.append("    "+line.strip())
        out.append("}")
    return "\n".join(out)+"\n"


def apply_waf(cfg=None):
    return _save_sites(_load_sites())


def _ensure_include():
    path=_cfg()
    with open(path,encoding="utf-8") as f: text=f.read()
    inc=f"    include {_sites_conf()};"
    if inc not in text:
        pos=text.rfind("}")
        text=text[:pos]+inc+"\n"+text[pos:]
        with open(path,"w",encoding="utf-8") as f: f.write(text)


def _save_sites(sites, reload_=True):
    os.makedirs(os.path.dirname(_sites_conf()),exist_ok=True); _ensure_include()
    old_conf=open(_sites_conf(),encoding="utf-8").read() if os.path.isfile(_sites_conf()) else None
    old_state=open(_sites_state(),encoding="utf-8").read() if os.path.isfile(_sites_state()) else None
    try:
        # 站点开启了下载路由时先确保路由文件存在，否则 include 会导致校验失败
        if _routes_enabled(sites) and not os.path.isfile(_routes_conf()):
            with open(_routes_conf(),"w",encoding="utf-8") as f: f.write(_gen_routes_conf())
        with open(_sites_conf(),"w",encoding="utf-8") as f: f.write(_render_sites(sites))
        validate()
        for path,data in ((_sites_state(),json.dumps(sites,ensure_ascii=False,indent=2)),):
            fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path)); os.close(fd)
            with open(tmp,"w",encoding="utf-8") as f: f.write(data)
            os.replace(tmp,path)
        if reload_: reload()
    except BaseException:
        if old_conf is None:
            try: os.remove(_sites_conf())
            except OSError: pass
        else:
            with open(_sites_conf(),"w",encoding="utf-8") as f: f.write(old_conf)
        if old_state is not None:
            with open(_sites_state(),"w",encoding="utf-8") as f: f.write(old_state)
        raise
    return {"sites":sites,"path":_sites_conf()}


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
    if _method()=="container":
        rt=_runtime(); run([rt,"rm","-f",CONTAINER],check=False)
        run([rt,"run","-d","--name",CONTAINER,"--restart","unless-stopped","--network","host","-v",f"{config.plugin_dir('nginx','config')}:{config.plugin_dir('nginx','config')}","-v",f"{config.plugin_dir('nginx','data')}:{config.plugin_dir('nginx','data')}","-v",f"{config.plugin_dir('nginx','runtime')}:{config.plugin_dir('nginx','runtime')}:ro",IMAGE,"nginx","-c",_cfg(),"-g","daemon off;"],check=True)
    else: run([_bin(), "-c", _cfg()], check=True)


def _stop():
    if _method()=="container":
        try: run([_runtime(),"rm","-f",CONTAINER],check=False)
        except AppError: pass
        return
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
    if _method()=="container":
        try: running=run([_runtime(),"inspect",CONTAINER]).returncode==0
        except AppError: running=False
    else: running = os.path.isfile(_pid())
    ver = None
    if deployed:
        r = run([bin_path, "-v"])
        ver = (r.stderr or r.stdout or "").strip()
    return {"name": "nginx", "installed": deployed or has_cmd("nginx"),
            "deployed": deployed, "running": running, "version": ver,
            "binary": bin_path, "config_file": _cfg(), **deploy_info(),
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
    if _method()=="container":
        if not os.path.isfile(_cfg()): _write_config()
        run([_runtime(),"pull",IMAGE],check=True); _start()
        return {"ok":True,"source":"container","message":"Nginx 容器已启动，配置与数据目录保持不变",**status()}
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


def post_install():
    """市场安装后自动部署 nginx 二进制并启动。"""
    bin_path = _bin()
    if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
        return {"skipped": True, "message": f"nginx 已安装: {bin_path}"}
    return install()


def remove():
    """卸载：停止面板部署的 nginx，删除运行时二进制（保留 config/data，由市场 keep_data 决定）。"""
    _stop()
    shutil.rmtree(config.plugin_dir("nginx", "runtime"), ignore_errors=True)
    return {"name": "nginx", "removed": True}


def stop():
    """停用插件：停止面板部署的 nginx 服务（保留配置/数据/二进制）。"""
    _stop()
    return {"name": "nginx", "stopped": True}


def set_deploy_method(method, runtime=None):
    if method not in ("host","container"): raise AppError("部署方式仅支持 host/container")
    old=_method(); _stop(); params=_params(); params["deploy_method"]=method
    if runtime: params["container_runtime"]=runtime
    config.set_plugin_params("nginx",params)
    try: return install()
    except BaseException:
        params["deploy_method"]=old; config.set_plugin_params("nginx",params)
        try: _start()
        except BaseException: pass
        raise


def start():
    """重新启用插件：启动面板部署的 nginx 服务。"""
    if os.path.isfile(_bin()) and os.path.isfile(_cfg()):
        _start()
    return {"name": "nginx", "started": True}


def show():
    try:
        with open(_cfg(), encoding="utf-8") as f: return {"content":f.read(),"path":_cfg()}
    except OSError: return {"content":"","path":_cfg()}


def validate():
    if _method()=="container":
        rt=_runtime(); r=run([rt,"run","--rm","--network","host","-v",f"{config.plugin_dir('nginx','config')}:{config.plugin_dir('nginx','config')}:ro","-v",f"{config.plugin_dir('nginx','data')}:{config.plugin_dir('nginx','data')}","-v",f"{config.plugin_dir('nginx','runtime')}:{config.plugin_dir('nginx','runtime')}:ro",IMAGE,"nginx","-t","-c",_cfg()])
    else:
        if not os.path.isfile(_bin()): raise AppError("nginx 尚未部署")
        r=run([_bin(),"-t","-c",_cfg()])
    if r.returncode != 0: raise AppError((r.stderr or r.stdout or "nginx 配置校验失败").strip())
    return {"ok":True,"message":(r.stderr or r.stdout or "配置有效").strip()}


def reload():
    validate()
    if _method()=="container": run([_runtime(),"exec",CONTAINER,"nginx","-s","reload"],check=True)
    else: run([_bin(),"-c",_cfg(),"-s","reload"],check=True)
    return {"reloaded":True}


def apply(reload=True):
    """应用配置（download_route 能力入口）：刷新托管下载路由 → 校验 → 按需 reload。

    与 caddy 后端语义一致：托管内容无变化时跳过 reload，周期同步可安全高频
    执行；无开启下载路由的站点时仅刷新路由（no-op）并校验现有配置。
    """
    routes = _refresh_routes()
    result = validate()
    result["routes"] = routes
    if reload and routes.get("changed"):
        result.update(globals()["reload"]())
        result["reloaded"] = True
    else:
        result["reloaded"] = False
    return result


# ---------- 下载路由（download_route 能力，与 caddy 后端对齐） ----------

_ROUTES_BEGIN = "# >>> AUPS APPS (managed, do not remove) <<<"
_ROUTES_END = "# <<< AUPS APPS >>>"


def _routes_conf():
    return os.path.join(config.plugin_dir("nginx", "config"), "aups-routes.conf")


def _routes_enabled(sites):
    return any((s.get("options") or {}).get("download_routes") for s in sites or [])


def _routes_data():
    """渲染前实时重取 appupdate 公共数据块（CI 经 SSH 直传不经面板，落盘块可能
    滞后）；appupdate 停用/缺失时退回已落盘数据块。"""
    from ...core import contracts
    try:
        data = contracts.call("nginx", "appupdate", "download_routes")
        if data is not None:
            return data
    except Exception:
        pass
    try:
        return contracts.read_data("nginx", "appupdate", "download_routes") or {"apps": []}
    except Exception:
        return {"apps": []}


def _gen_routes_conf():
    """从 appupdate 公共数据生成下载路由片段（location 精确匹配 + 302）。

    versions 按版本号降序渲染版本短链；latest 优先取数据块 latest 字段
    （appupdate 按文件日期选定），缺省回退版本号最大的文件。同一版本多个
    文件时只保留首个（版本序最高），避免 location 重复导致校验失败。
    """
    out = [_ROUTES_BEGIN]
    seen = set()
    for app in _routes_data().get("apps", []):
        host = app["name"]
        vers = app.get("versions", [])
        latest = app.get("latest") or (vers[0] if vers else None)
        if not latest:
            continue
        out.append(f"    # -- {host} --")
        for v in vers:
            ver = str(v.get("version") or "")
            dl = f"/{host}/{v['rel']}"
            if not ver or not v.get("rel") or ver in seen:
                continue
            seen.add(ver)
            for u in (f"/{host}/{ver}", f"/{host}/v{ver}"):
                out.append(f"    location = {u} {{ return 302 {dl}; }}")
        rel = latest.get("rel")
        if rel:
            out.append(f"    location = /{host}/latest {{ return 302 /{host}/{rel}; }}")
    out.append(_ROUTES_END)
    return "\n".join(out) + "\n"


def _refresh_routes():
    """重写 aups-routes.conf（内容无变化时跳过）。返回 {changed/skipped/reason}。"""
    if not _routes_enabled(_load_sites()):
        return {"skipped": True,
                "reason": "无开启「下载路由」的文件服务站点（站点设置 download_routes）"}
    new = _gen_routes_conf()
    old = None
    if os.path.isfile(_routes_conf()):
        with open(_routes_conf(), encoding="utf-8") as f:
            old = f.read()
    if old == new:
        return {"changed": False}
    os.makedirs(os.path.dirname(_routes_conf()), exist_ok=True)
    with open(_routes_conf(), "w", encoding="utf-8") as f:
        f.write(new)
    return {"changed": True}


def preview():
    """下载路由预览（供 appupdate 反代预览与排查）。"""
    return {"apps": _gen_routes_conf(),
            "path": _routes_conf(),
            "enabled": _routes_enabled(_load_sites())}


def clear_routes(reload=True):
    """清空托管下载路由（appupdate 迁移到其他反代时调用）。

    路由文件清为空标记区，站点「下载路由」开关保留：切回 nginx 后执行
    apply() 即可按最新数据重新生成路由。
    """
    empty = _ROUTES_BEGIN + "\n" + _ROUTES_END + "\n"
    old = None
    if os.path.isfile(_routes_conf()):
        with open(_routes_conf(), encoding="utf-8") as f:
            old = f.read()
    changed = old != empty
    if changed:
        os.makedirs(os.path.dirname(_routes_conf()), exist_ok=True)
        with open(_routes_conf(), "w", encoding="utf-8") as f:
            f.write(empty)
    reloaded = False
    if changed and reload and _routes_enabled(_load_sites()):
        validate()
        reload_fn = globals()["reload"]
        reload_fn()
        reloaded = True
    return {"cleared": True, "changed": changed, "reloaded": reloaded}


def update_app_sites(apps, reload_=True):
    """更新应用站点（appupdate 托管，aups_app 标记）：域名 → 文件服务 + 域名校验。

    只增删改带 aups_app 标记的条目，用户自建站点不动；域名与用户站点冲突时
    跳过并记录。内容无变化时跳过写盘与 reload。
    """
    sites = _load_sites()
    keep = [s for s in sites if not s.get("aups_app")]
    reserved = {s.get("host") for s in keep}
    managed, skipped = [], []
    seen = set(reserved)
    for app in apps or []:
        name = (app.get("name") or "").strip()
        domain = (app.get("domain") or "").strip().lower()
        workdir = (app.get("workdir") or app.get("dir") or "").strip()
        if not name or not domain or not workdir:
            continue
        if domain in seen:
            skipped.append(domain)
            continue
        seen.add(domain)
        managed.append({"host": domain, "mode": "file_server", "target": workdir,
                        "extra": ('location = /.well-known/aups-domain-check '
                                  f'{{ return 200 "aups-domain-verify:{name}"; }}'),
                        "options": {}, "aups_app": True, "app": name})
    new_sites = keep + managed
    if new_sites == sites:
        return {"updated": True, "unchanged": True,
                "sites": len(managed), "skipped_existing": skipped}
    _save_sites(new_sites, reload_=reload_)
    return {"updated": True, "unchanged": False,
            "sites": len(managed), "skipped_existing": skipped}


def save_config(content, reload_=True):
    """保存完整 nginx.conf：写盘 → 校验（失败恢复旧内容）→ 按需 reload。"""
    content = (content or "").replace("\r\n", "\n")
    cfg = _cfg()
    old = None
    if os.path.isfile(cfg):
        with open(cfg, encoding="utf-8") as f:
            old = f.read()
    try:
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(content)
        result = validate()
    except BaseException:
        if old is not None:
            with open(cfg, "w", encoding="utf-8") as f:
                f.write(old)
        raise
    if reload_:
        try:
            result.update(globals()["reload"]())
        except BaseException:
            if old is not None:
                with open(cfg, "w", encoding="utf-8") as f:
                    f.write(old)
            raise AppError("nginx reload 失败，已恢复旧配置")
    return result


def instance(action):
    """实例控制：start/stop/restart/reload（实机与容器通用）。"""
    if action == "reload":
        globals()["reload"]()
    elif action == "start":
        if _method() != "container" and not os.path.isfile(_bin()):
            raise AppError("nginx 尚未部署")
        _start()
    elif action == "stop":
        _stop()
    elif action == "restart":
        _stop()
        _start()
    else:
        raise AppError("action 需为 start/stop/restart/reload")
    return {**status(), "action": action}


def list_sites(): return {"sites":_load_sites(),"path":_sites_conf()}
def create_site(host,mode="reverse_proxy",target="",extra="",options=None):
    host=_domain(host); sites=_load_sites()
    if any(x.get("host")==host for x in sites): raise AppError(f"站点 {host} 已存在")
    if mode not in ("reverse_proxy","file_server") or not target: raise AppError("站点类型或目标无效")
    item={"host":host,"mode":mode,"target":target,"extra":extra or "","options":options or {}}
    sites.append(item); _save_sites(sites); return item
def update_site(host,mode=None,target=None,extra=None,options=None):
    host=_domain(host); sites=_load_sites(); item=next((x for x in sites if x.get("host")==host),None)
    if not item: raise AppError(f"站点 {host} 不存在")
    if mode is not None: item["mode"]=mode
    if target is not None: item["target"]=target
    if extra is not None: item["extra"]=extra
    if options is not None: item["options"]=options
    _save_sites(sites); return item
def delete_site(host):
    host=_domain(host); sites=_load_sites(); new=[x for x in sites if x.get("host")!=host]
    if len(new)==len(sites): raise AppError(f"站点 {host} 不存在")
    _save_sites(new); return {"host":host,"deleted":True}
def logs(kind="access",limit=200):
    if _method()=="container":
        r=run([_runtime(),"logs","--tail",str(max(1,min(int(limit),2000))),CONTAINER]); return {"kind":kind,"source":"container","lines":(r.stdout or r.stderr or "").splitlines()}
    name="error.log" if kind=="error" else "access.log"; path=os.path.join(config.plugin_dir("nginx","data"),name)
    try:
        with open(path,encoding="utf-8",errors="replace") as f: lines=f.readlines()[-max(1,min(int(limit),2000)):]
    except OSError: lines=[]
    return {"kind":kind,"path":path,"lines":[x.rstrip("\n") for x in lines]}
