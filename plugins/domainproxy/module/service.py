import json, os, re, subprocess, sys
from pathlib import Path
from ... import config
from ...core import rproxy
from ...errors import AppError

UNIT = "/etc/systemd/system/aups-domainproxy.service"
def _path(): return Path(config.plugin_dir("domainproxy", "config")) / "config.json"
def read_config():
    try: return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError): return {"domain":"", "prefix":"proxy", "port":18765, "backend":"caddy"}
def status():
    c = read_config(); running = False
    if os.path.exists("/run/systemd/system"):
        running = subprocess.run(["systemctl","is-active","aups-domainproxy"], capture_output=True).returncode == 0
    base = "https://" + c["domain"] + "/" if c.get("domain") else ""
    available=[]
    for item in rproxy.backend_list().get("backends", []):
        if "sites" in (item.get("capabilities") or []): available.append({"name":item["name"],"title":item.get("title") or item["name"]})
    return {**c, "running":running, "backends":available, "url":base + ((c.get("prefix", "").strip("/") + "/") if c.get("prefix") else "") + "https://github.com/"}
def configure(domain="", prefix="proxy", port=18765, backend="caddy"):
    domain = domain.strip().lower(); prefix = prefix.strip().strip("/"); port = int(port)
    if not re.fullmatch(r"[a-z0-9.-]+", domain): raise AppError("域名格式无效")
    if prefix and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", prefix): raise AppError("入口前缀格式无效")
    if not 1024 <= port <= 65535: raise AppError("内部端口需为 1024-65535")
    old = read_config(); data = {"domain":domain,"prefix":prefix,"port":port,"backend":backend}
    try:
        if old.get("domain") == domain and old.get("backend") == backend: rproxy.site_update(backend, domain, mode="reverse_proxy", target=f"127.0.0.1:{port}")
        else:
            rproxy.site_create(backend, domain, mode="reverse_proxy", target=f"127.0.0.1:{port}")
            if old.get("domain"):
                try: rproxy.site_delete(old.get("backend", backend), old["domain"])
                except Exception: pass
    except Exception as e: raise AppError("反代站点配置失败: " + str(e))
    _path().parent.mkdir(parents=True, exist_ok=True); tmp = _path().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8"); os.replace(tmp, _path())
    return start()
def start():
    text = "[Unit]\nDescription=AUPS Domain Proxy\nAfter=network-online.target\n[Service]\nExecStart=" + sys.executable + " -m aups.modules.domainproxy.server\nRestart=on-failure\nUser=root\n[Install]\nWantedBy=multi-user.target\n"
    Path(UNIT).write_text(text, encoding="utf-8")
    subprocess.run(["systemctl","daemon-reload"], check=True); subprocess.run(["systemctl","enable","--now","aups-domainproxy"], check=True)
    return status()
def stop():
    subprocess.run(["systemctl","disable","--now","aups-domainproxy"], check=False)
    return {**read_config(), "running":False}
def remove():
    old=read_config(); result=stop()
    if old.get("domain") and old.get("backend"):
        try: rproxy.site_delete(old["backend"],old["domain"])
        except Exception: pass
    return result
