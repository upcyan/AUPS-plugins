MANIFEST={
 "name":"traefik","title":"Traefik","version":"1.0.0","type":"external","attr":["依赖","网络"],
 "description":"Docker/Podman 原生动态反代 provider","proxy":"traefik","provides":{"proxy":"traefik"},
 "rproxy_module":"aups.modules.traefik.api","capabilities":["status","show","apply","reload","sites","validate","logs","upstreams","tls","websocket","health_check","tcp","deploy_switch"],
 "config_dir":"traefik","data_dir":"traefik","deploy":{"container":{"kinds":["docker","podman"]}},
 "api_module":"aups.modules.traefik.webapi","api_paths":["/api/traefik/status","/api/traefik/install","/api/traefik/validate","/api/traefik/reload","/api/traefik/logs","/api/traefik/deploy"],
 "entry":[{"id":"main","title":"Traefik"}],"plugins":[{"id":"main","title":"Traefik","description":"容器发现、动态路由与实例管理"}]
}
def post_install():
 from . import api
 return api.install()
def start():
 from . import api
 return api.start()
def stop():
 from . import api
 return api.stop()
def remove():
 from . import api
 return api.remove()
