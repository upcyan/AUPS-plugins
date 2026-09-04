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
        if s.get("mode")=="file_server": out.extend([f"    root {target};","    index index.html;"])
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


def _save_sites(sites):
    os.makedirs(os.path.dirname(_sites_conf()),exist_ok=True); _ensure_include()
    old_conf=open(_sites_conf(),encoding="utf-8").read() if os.path.isfile(_sites_conf()) else None
    old_state=open(_sites_state(),encoding="utf-8").read() if os.path.isfile(_sites_state()) else None
    try:
        with open(_sites_conf(),"w",encoding="utf-8") as f: f.write(_render_sites(sites))
        validate()
        for path,data in ((_sites_state(),json.dumps(sites,ensure_ascii=False,indent=2)),):
            fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path)); os.close(fd)
            with open(tmp,"w",encoding="utf-8") as f: f.write(data)
            os.replace(tmp,path)
        reload()
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
    if not os.path.isfile(_bin()): raise AppError("nginx 尚未部署")
    r=run([_bin(),"-t","-c",_cfg()])
    if r.returncode != 0: raise AppError((r.stderr or r.stdout or "nginx 配置校验失败").strip())
    return {"ok":True,"message":(r.stderr or r.stdout or "配置有效").strip()}


def reload():
    validate(); run([_bin(),"-c",_cfg(),"-s","reload"],check=True); return {"reloaded":True}


def apply(reload=True):
    result=validate()
    if reload: result.update(globals()["reload"]())
    return result


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
    name="error.log" if kind=="error" else "access.log"; path=os.path.join(config.plugin_dir("nginx","data"),name)
    try:
        with open(path,encoding="utf-8",errors="replace") as f: lines=f.readlines()[-max(1,min(int(limit),2000)):]
    except OSError: lines=[]
    return {"kind":kind,"path":path,"lines":[x.rstrip("\n") for x in lines]}
