"""nginx 插件清单：Nginx 反代依赖（属性=依赖）。"""

MANIFEST = {
    "name": "nginx",
    "title": "Nginx 依赖",
    "version": "0.1.0",
    "description": "Nginx 反代：站点配置、证书（通过 certbot/acme 申请）",
    "type": "external",
    "attr": "依赖",
    "proxy": "nginx",
    "config_dir": "nginx",
    "data_dir": "nginx",
    "cli_groups": ["nginx"],
    "api_module": "aups.modules.nginx.webapi",
    "api_paths": ["/api/nginx", "/api/nginx/status", "/api/nginx/install", "/api/nginx/remove"],
    "plugins": [
        {"id": "main", "title": "Nginx 反代", "description": "Nginx 状态、安装与卸载（部署到面板目录）"},
    ],
}
