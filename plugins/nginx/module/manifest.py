"""nginx 插件清单：Nginx 反代依赖（属性=依赖）。"""

MANIFEST = {
    "name": "nginx",
    "title": "Nginx 依赖",
    "version": "1.1.0",
    "description": "Nginx 反代：站点配置、证书（通过 certbot/acme 申请）",
    "type": "external",
    "attr": "依赖",
    "proxy": "nginx",
    "provides": {"proxy": "nginx", "waf": "nginx"},
    "rproxy_module": "aups.modules.nginx.api",
    "capabilities": ["status", "show", "apply", "reload", "sites", "validate", "logs", "upstreams", "tls", "websocket", "waf"],
    "config_dir": "nginx",
    "data_dir": "nginx",
    "cli_groups": ["nginx"],
    "api_module": "aups.modules.nginx.webapi",
    "api_paths": ["/api/nginx/status", "/api/nginx/install", "/api/nginx/remove", "/api/nginx/config", "/api/nginx/validate", "/api/nginx/reload", "/api/nginx/logs"],
    "entry": [
        {"id": "main", "title": "Nginx 反代"},
    ],
    "plugins": [
        {"id": "main", "title": "Nginx 反代", "description": "Nginx 状态、安装与卸载（部署到面板目录）"},
    ],
}
