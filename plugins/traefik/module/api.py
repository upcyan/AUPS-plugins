import json, os, re, shutil, tempfile
from pathlib import Path
from ... import config
from ...errors import AppError
from ...util import has_cmd, run
from ...core import waf

IMAGE="traefik:v3.3"; NAME="aups-traefik"
def _dir(): return Path(config.plugin_dir("traefik","config"))
def _data(): return Path(config.plugin_dir("traefik","data"))
def _state(): return _dir()/"sites.json"
def _runtime():
 p=config.get_plugin_params("traefik") or {}; chosen=p.get("runtime")
 if chosen in ("docker","podman") and has_cmd(chosen): return chosen
 for n in ("docker","podman"):
  if has_cmd(n): return n
 raise AppError("需要 Docker 或 Podman")
def set_deploy_method(method):
 if method not in ("docker","podman") or not has_cmd(method): raise AppError("容器运行时不可用")
 p=config.get_plugin_params("traefik") or {}; p["runtime"]=method; config.set_plugin_params("traefik",p); return install()
def deploy_info(): return {"method":"container","kind":_runtime(),"config_shared":True,"data_shared":True}
def _load():
 try:
  d=json.loads(_state().read_text(encoding="utf-8")); return d if isinstance(d,list) else []
 except (OSError,ValueError): return []
def _host(v):
 v=(v or "").strip().lower()
 if not re.fullmatch(r"(?:\*\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?",v): raise AppError("站点域名无效")
 return v
def _q(v): return '"'+str(v).replace('\\','\\\\').replace('"','\\"')+'"'
def _target(v):
 v=str(v or ""); host="host.docker.internal" if _runtime()=="docker" else "host.containers.internal"
 return re.sub(r"^(https?://)?(?:127\.0\.0\.1|localhost)",lambda m:(m.group(1) or "")+host,v)
def _certs(host,tls):
 cert,key=tls.get("cert"),tls.get("key")
 if not (cert and key): return None
 if not (os.path.isfile(cert) and os.path.isfile(key)): raise AppError("TLS 证书或私钥不存在")
 d=_dir()/"certs"; d.mkdir(parents=True,exist_ok=True); base=re.sub(r"[^a-z0-9.-]","_",host)
 out=[]
 for src,suffix in ((cert,".crt"),(key,".key")):
  dst=d/(base+suffix); shutil.copy2(src,dst); os.chmod(dst,0o600 if suffix==".key" else 0o644); out.append("/etc/traefik/certs/"+dst.name)
 return out
def _static(sites=None):
 rt=_runtime(); socket="/var/run/docker.sock" if rt=="docker" else "/var/run/podman/podman.sock"
 text="entryPoints:\n  web:\n    address: :80\n  websecure:\n    address: :443\n"
 for i,s in enumerate(x for x in (sites or []) if x.get("mode")=="tcp"):
  port=int((s.get("options") or {}).get("listen_port",0))
  if not port: raise AppError("TCP 路由需要 listen_port")
  text+=f"  tcp{i}:\n    address: :{port}\n"
 return text+"providers:\n  file:\n    filename: /etc/traefik/dynamic.yml\n    watch: true\n  docker:\n    endpoint: unix://"+socket+"\n    exposedByDefault: false\napi:\n  dashboard: false\nlog:\n  level: INFO\naccessLog: {}\n"
def _dynamic(sites):
 wc=waf.render_config(); waf_on=bool(wc.get("enabled")); lines=["http:","  routers:"]; services=[]; certs=[]; tcp=[]
 for i,s in enumerate(x for x in sites if x.get("mode")!="tcp"):
  o=s.get("options") or {}; tls=o.get("tls") or {}; name=f"site{i}"
  lines += [f"    {name}:",f"      rule: Host(`{s['host']}`)","      entryPoints:","        - websecure" if tls else "        - web",f"      service: {name}"]
  if waf_on and ((wc.get("whitelist_ips") or []) or (wc.get("rate_limit") or {}).get("enabled")): lines += ["      middlewares:","        - aups-waf"]
  if tls: lines.append("      tls: {}")
  ups=o.get("upstreams") or [{"target":s.get("target")}]
  services += [f"    {name}:","      loadBalancer:","        healthCheck:",f"          path: {_q(o.get('health_path','/'))}",f"          interval: {_q(str(o.get('health_interval',10))+'s')}","        servers:"]
  for u in ups:
   if u.get("target"):
    target=_target(u["target"]); services.append(f"          - url: {_q(('http://' if '://' not in target else '')+target)}")
  pair=_certs(s["host"],tls)
  if pair: certs += ["    - certFile: "+_q(pair[0]),"      keyFile: "+_q(pair[1])]
 lines += ["  services:"] + services
 if waf_on and ((wc.get("whitelist_ips") or []) or (wc.get("rate_limit") or {}).get("enabled")):
  lines += ["  middlewares:","    aups-waf:","      chain:","        middlewares:"]
  if wc.get("whitelist_ips"): lines.append("          - aups-waf-allow")
  if (wc.get("rate_limit") or {}).get("enabled"): lines.append("          - aups-waf-rate")
  if wc.get("whitelist_ips"):
   lines += ["    aups-waf-allow:","      ipAllowList:","        sourceRange:"]+[f"          - {_q(ip)}" for ip in wc["whitelist_ips"]]
  if (wc.get("rate_limit") or {}).get("enabled"):
   rl=wc["rate_limit"]; lines += ["    aups-waf-rate:","      rateLimit:",f"        average: {max(1,int(rl.get('requests',60)))}",f"        burst: {max(1,int(rl.get('requests',60)))}"]
 if certs: lines += ["tls:","  certificates:"]+certs
 for i,s in enumerate(x for x in sites if x.get("mode")=="tcp"):
  port=int((s.get("options") or {}).get("listen_port",0)); tcp.append((i,s,port))
 if tcp:
  lines += ["tcp:","  routers:"]
  for i,s,p in tcp: lines += [f"    tcp{i}:","      rule: HostSNI(`*`)",f"      entryPoints: [tcp{i}]",f"      service: tcp{i}"]
  lines += ["  services:"]
  for i,s,p in tcp: lines += [f"    tcp{i}:","      loadBalancer:","        servers:",f"          - address: {_q(_target(s['target']))}"]
 return "\n".join(lines)+"\n"
def apply_waf(cfg=None): return _save(_load())
def _write_base(sites=None):
 sites=sites if sites is not None else _load(); _dir().mkdir(parents=True,exist_ok=True); _data().mkdir(parents=True,exist_ok=True); (_dir()/"traefik.yml").write_text(_static(sites),encoding="utf-8")
 if not (_dir()/"dynamic.yml").exists(): (_dir()/"dynamic.yml").write_text(_dynamic(sites),encoding="utf-8")
def validate():
 _write_base(); rt=_runtime(); cmd=[rt,"run","--rm","-v",f"{_dir()}:/etc/traefik:ro",IMAGE,"check-config","--configFile=/etc/traefik/traefik.yml"]
 r=run(cmd)
 if r.returncode: raise AppError((r.stderr or r.stdout or "Traefik 配置无效").strip())
 return {"ok":True,"message":(r.stdout or r.stderr or "配置有效").strip()}
def _save(sites):
 _write_base(sites); path=_dir()/"dynamic.yml"; old=path.read_text(encoding="utf-8") if path.exists() else None; path.write_text(_dynamic(sites),encoding="utf-8")
 try: validate()
 except BaseException:
  if old is None: path.unlink(missing_ok=True)
  else: path.write_text(old,encoding="utf-8")
  raise
 fd,tmp=tempfile.mkstemp(dir=_dir()); os.close(fd); Path(tmp).write_text(json.dumps(sites,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,_state()); start(); return {"sites":sites,"path":str(path)}
def install(): _write_base(); run([_runtime(),"pull",IMAGE],check=True); return start()
def start():
 rt=_runtime(); stop(); socket="/var/run/docker.sock" if rt=="docker" else "/run/podman/podman.sock"
 cmd=[rt,"run","-d","--name",NAME,"--restart","unless-stopped","-p","80:80","-p","443:443"]
 for s in _load():
  if s.get("mode")=="tcp":
   port=int((s.get("options") or {}).get("listen_port",0)); cmd += ["-p",f"{port}:{port}"]
 if rt=="docker": cmd += ["--add-host","host.docker.internal:host-gateway"]
 cmd += ["-v",f"{_dir()}:/etc/traefik:ro","-v",f"{socket}:{socket}:ro",IMAGE,"--configFile=/etc/traefik/traefik.yml"]
 run(cmd,check=True); return status()
def stop():
 try: rt=_runtime(); run([rt,"rm","-f",NAME],check=False)
 except AppError: pass
 return {"stopped":True}
def remove(): stop(); return {"removed":True}
def status():
 rt=_runtime(); r=run([rt,"inspect",NAME]); return {"name":"traefik","installed":True,"running":r.returncode==0,"runtime":rt,"image":IMAGE,"sites":len(_load()),"config_file":str(_dir()/"dynamic.yml")}
def show():
 p=_dir()/"dynamic.yml"; return {"path":str(p),"content":p.read_text(encoding="utf-8") if p.exists() else ""}
def reload(): return {"reloaded":True,"method":"file-watch"}
def apply(reload=True): return validate()
def list_sites(): return {"sites":_load(),"path":str(_dir()/"dynamic.yml")}
def create_site(host,mode="reverse_proxy",target="",extra="",options=None):
 host=_host(host); sites=_load()
 if any(x["host"]==host for x in sites): raise AppError("站点已存在")
 if mode not in ("reverse_proxy","tcp"): raise AppError("Traefik 支持 reverse_proxy/tcp")
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
 r=run([_runtime(),"logs","--tail",str(max(1,min(int(limit),2000))),NAME]); return {"kind":kind,"source":"container","lines":((r.stdout or r.stderr or "").splitlines())}
