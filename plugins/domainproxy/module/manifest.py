MANIFEST = {
    "name": "domainproxy", "title": "域名代理", "version": "1.2.0", "type": "external",
    "attr": ["功能", "网络"], "config_dir": "domainproxy", "data_dir": "domainproxy",
    "description": "受控代理 GitHub 与 Docker Registry，不提供任意 URL 转发",
    "api_module": "aups.modules.domainproxy.webapi", "api_paths": ["/api/domainproxy/status", "/api/domainproxy/config", "/api/domainproxy/start", "/api/domainproxy/stop"],
    "depends": [{"capability": "proxy"}], "entry": [{"id":"main","title":"域名代理"}],
    "plugins": [{"id":"main","title":"域名代理","description":"GitHub / Docker 受控代理"}],
}

def start():
    from . import service
    return service.start()

def stop():
    from . import service
    return service.stop()

def remove():
    from . import service
    return service.remove()
