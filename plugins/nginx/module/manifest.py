"""nginx 插件清单：Nginx 反代环境（属性=环境）。"""

MANIFEST = {
    "name": "nginx",
    "title": "Nginx 环境",
    "version": "0.1.0",
    "description": "Nginx 反代：站点配置、证书（通过 certbot/acme 申请）",
    "type": "external",
    "attr": "环境",
    "proxy": "nginx",
    "config_dir": "nginx",
    "data_dir": "nginx",
    "cli_groups": ["nginx"],
    "api_module": "aups.modules.nginx.webapi",
    "api_paths": ["/api/nginx", "/api/nginx/status", "/api/nginx/install"],
    "plugins": [
        {"id": "main", "title": "Nginx 反代", "description": "Nginx 状态与安装"},
    ],
}
