import json, os, re, shutil, subprocess, tempfile
from pathlib import Path
from ... import config, pkg
from ...errors import AppError
from ...util import has_cmd, run
from ...core import waf

UNIT="/etc/systemd/system/aups-haproxy.service"
def _bin(): return os.path.join(config.plugin_dir("haproxy","runtime"),"haproxy")
def _cfg(): return os.path.join(config.plugin_dir("haproxy","config"),"haproxy.cfg")
def _state(): return os.path.join(config.plugin_dir("haproxy","config"),"sites.json")
def _data(): return config.plugin_dir("haproxy","data")
def _load():
 try:
  with open(_state(),encoding="utf-8") as f: d=json.load(f)
  return d if isinstance(d,list) else []
 except (OSError,ValueError): return []
def _host(v):
 v=(v or "").strip().lower()
 if not re.fullmatch(r"(?:\*\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?",v): raise AppError("站点域名无效")
 return v
def _pem(site):
 tls=(site.get("options") or {}).get("tls") or {}; cert,key=tls.get("cert"),tls.get("key")
 if not (cert and key): return ""
 if not (os.path.isfile(cert) and os.path.isfile(key)): raise AppError("TLS 证书或私钥不存在")
 out=os.path.join(_data(),"certs",re.sub(r"[^a-z0-9.-]","_",site["host"])+".pem"); os.makedirs(os.path.dirname(out),exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=os.path.dirname(out)); os.close(fd)
 with open(tmp,"wb") as w:
  for p in (cert,key):
   with open(p,"rb") as r: shutil.copyfileobj(r,w)
 os.chmod(tmp,0o600); os.replace(tmp,out); return out
def _render(sites):
 lines=["global","    daemon","defaults","    mode http","    option httplog","    timeout connect 5s","    timeout client 60s","    timeout server 60s"]
 http=[x for x in sites if x.get("mode")!="tcp"]
 if http:
  wc=waf.render_config()
  tls=[_pem(x) for x in http if ((x.get("options") or {}).get("tls") or {}).get("cert")]
  lines += ["frontend aups_http","    bind *:80"]
  if tls: lines.append("    bind *:443 ssl crt "+" crt ".join(tls))
  if wc.get("enabled"):
   for i,ip in enumerate(wc.get("blacklist_ips") or []): lines += [f"    acl waf_deny_ip_{i} src {ip}",f"    http-request deny if waf_deny_ip_{i}"]
   if wc.get("whitelist_ips"):
    lines.append("    acl waf_allow_ip src "+" ".join(wc["whitelist_ips"])); lines.append("    http-request deny unless waf_allow_ip")
   for i,r in enumerate(wc.get("rules") or []):
    kind,pat,field=r.get("kind"),str(r.get("pattern","")).replace(" ","\\ "),r.get("field")
    expr={"path_regex":f"path_reg {pat}","user_agent":f"hdr_reg(User-Agent) {pat}","method":f"method_reg {pat}"}.get(kind)
    if kind=="header" and field and re.fullmatch(r"[A-Za-z0-9-]+",field): expr=f"hdr_reg({field}) {pat}"
    if kind=="query" and field and re.fullmatch(r"[A-Za-z0-9_]+",field): expr=f"urlp_reg({field}) {pat}"
    if expr: lines += [f"    acl waf_rule_{i} {expr}",f"    http-request deny if waf_rule_{i}"]
  for i,s in enumerate(http): lines += [f"    acl host_{i} hdr(host) -i {s['host']}",f"    use_backend web_{i} if host_{i}"]
  for i,s in enumerate(http):
   lines += [f"backend web_{i}","    mode http","    option httpchk GET /",f"    http-request set-header X-Forwarded-Proto https if {{ ssl_fc }}"]
   ups=(s.get("options") or {}).get("upstreams") or [{"target":s.get("target"),"weight":1}]
   for n,u in enumerate(ups):
    if u.get("target"): lines.append(f"    server srv{n} {u['target']} weight {max(1,int(u.get('weight',1)))} check inter {int(u.get('interval',10))}s")
 for i,s in enumerate(x for x in sites if x.get("mode")=="tcp"):
  port=int((s.get("options") or {}).get("listen_port",0));
  if not port: raise AppError("TCP 路由需要 listen_port")
  lines += [f"frontend tcp_{i}","    mode tcp",f"    bind *:{port}",f"    default_backend tcp_up_{i}",f"backend tcp_up_{i}","    mode tcp"]
  ups=(s.get("options") or {}).get("upstreams") or [{"target":s.get("target"),"weight":1}]
  for n,u in enumerate(ups):
   if u.get("target"): lines.append(f"    server srv{n} {u['target']} weight {max(1,int(u.get('weight',1)))} check")
 return "\n".join(lines)+"\n"
def apply_waf(cfg=None): return _save(_load())
def validate():
 r=run([_bin(),"-c","-f",_cfg()]);
 if r.returncode: raise AppError((r.stderr or r.stdout or "HAProxy 配置无效").strip())
 return {"ok":True,"message":(r.stdout or r.stderr or "配置有效").strip()}
def _save(sites):
 os.makedirs(os.path.dirname(_cfg()),exist_ok=True); old=Path(_cfg()).read_text(encoding="utf-8") if os.path.isfile(_cfg()) else None
 Path(_cfg()).write_text(_render(sites),encoding="utf-8")
 try: validate()
 except BaseException:
  if old is None: os.remove(_cfg())
  else: Path(_cfg()).write_text(old,encoding="utf-8")
  raise
 fd,tmp=tempfile.mkstemp(dir=os.path.dirname(_state())); os.close(fd); Path(tmp).write_text(json.dumps(sites,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,_state()); reload(); return {"sites":sites,"path":_cfg()}
def install():
 config.ensure_panel_dirs("haproxy"); src=shutil.which("haproxy")
 if not src: pkg.install(["haproxy"]); src=shutil.which("haproxy")
 if not src: raise AppError("HAProxy 安装失败")
 shutil.copy2(src,_bin()); os.chmod(_bin(),0o755)
 if not os.path.isfile(_cfg()): Path(_cfg()).write_text(_render([]),encoding="utf-8")
 return start()
def start():
 validate(); Path(UNIT).write_text(f"[Unit]\nDescription=AUPS HAProxy\nAfter=network-online.target\n[Service]\nExecStart={_bin()} -Ws -f {_cfg()} -p {_data()}/haproxy.pid\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n",encoding="utf-8"); run(["systemctl","daemon-reload"],check=True); run(["systemctl","enable","--now","aups-haproxy"],check=True); return status()
def stop(): run(["systemctl","disable","--now","aups-haproxy"],check=False); return {"stopped":True}
def remove(): stop(); shutil.rmtree(config.plugin_dir("haproxy","runtime"),ignore_errors=True); return {"removed":True}
def status():
 r=run(["systemctl","is-active","aups-haproxy"]) if has_cmd("systemctl") else None
 return {"name":"haproxy","installed":os.path.isfile(_bin()),"running":bool(r and r.returncode==0),"config_file":_cfg(),"sites":len(_load())}
def show(): return {"path":_cfg(),"content":Path(_cfg()).read_text(encoding="utf-8") if os.path.isfile(_cfg()) else ""}
def reload(): validate(); run(["systemctl","restart","aups-haproxy"],check=True); return {"reloaded":True}
def apply(reload=True): return globals()["reload"]() if reload else validate()
def list_sites(): return {"sites":_load(),"path":_cfg()}
def create_site(host,mode="reverse_proxy",target="",extra="",options=None):
 host=_host(host); sites=_load()
 if any(x["host"]==host for x in sites): raise AppError("站点已存在")
 if mode not in ("reverse_proxy","tcp"): raise AppError("HAProxy 支持 reverse_proxy/tcp")
 item={"host":host,"mode":mode,"target":target,"extra":extra or "","options":options or {}}; sites.append(item); _save(sites); return item
def update_site(host,mode=None,target=None,extra=None,options=None):
 sites=_load(); item=next((x for x in sites if x["host"]==_host(host)),None)
 if not item: raise AppError("站点不存在")
 if mode is not None:item["mode"]=mode
 if target is not None:item["target"]=target
 if extra is not None:item["extra"]=extra
 if options is not None:item["options"]=options
 _save(sites); return item
def delete_site(host):
 host=_host(host); sites=_load(); new=[x for x in sites if x["host"]!=host]
 if len(new)==len(sites): raise AppError("站点不存在")
 _save(new); return {"host":host,"deleted":True}
def logs(kind="access",limit=200):
 limit=max(1,min(int(limit),2000)); r=run(["journalctl","-u","aups-haproxy","-n",str(limit),"--no-pager"]) if has_cmd("journalctl") else None
 return {"kind":kind,"source":"journald","lines":((r.stdout or "").splitlines() if r else [])}
