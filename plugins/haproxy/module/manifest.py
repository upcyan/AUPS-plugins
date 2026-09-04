MANIFEST={
 "name":"haproxy","title":"HAProxy","version":"1.1.0","type":"external","attr":["依赖","网络"],
 "description":"HTTP/TCP 反代与负载均衡 provider","proxy":"haproxy","provides":{"proxy":"haproxy","waf":"haproxy"},
 "rproxy_module":"aups.modules.haproxy.api","capabilities":["status","show","apply","reload","sites","validate","logs","upstreams","tls","websocket","health_check","tcp","deploy_switch","waf"],
 "config_dir":"haproxy","data_dir":"haproxy","deploy":{"host":True},"cli_groups":["haproxy"],
 "api_module":"aups.modules.haproxy.webapi","api_paths":["/api/haproxy/status","/api/haproxy/install","/api/haproxy/validate","/api/haproxy/reload","/api/haproxy/logs"],
 "entry":[{"id":"main","title":"HAProxy"}],"plugins":[{"id":"main","title":"HAProxy","description":"实例、配置、校验与日志"}]
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
