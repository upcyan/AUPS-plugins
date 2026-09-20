"""nginx 插件清单：Nginx 反代依赖（属性=依赖）。

v1.2.0：容器部署（docker/podman）、deploy_switch 能力。
v1.3.0：与 caddy 后端能力对齐——download_route（托管下载路由 aups-routes.conf，
latest 按文件日期、apply 无变化跳过 reload）、preview、clear_routes（迁移清理）、
update_app_sites（应用站点托管）；前端补齐站点管理/实例控制 UI。
"""

MANIFEST = {
    "name": "nginx",
    "title": "Nginx 依赖",
    "version": "1.3.0",
    "description": "Nginx 反代：站点管理、托管下载路由、实例控制、证书（通过 certbot/acme 申请）",
    "type": "external",
    "attr": "依赖",
    "proxy": "nginx",
    "provides": {"proxy": "nginx", "waf": "nginx"},
    "rproxy_module": "aups.modules.nginx.api",
    "capabilities": ["status", "show", "preview", "apply", "reload", "sites", "validate", "logs",
                     "upstreams", "tls", "websocket", "waf", "deploy_switch",
                     "download_route", "clear_routes"],
    "deploy": {"host": True, "container": {"kinds": ["docker", "podman"]}},
    "config_dir": "nginx",
    "data_dir": "nginx",
    "cli_groups": ["nginx"],
    "api_module": "aups.modules.nginx.webapi",
    "api_paths": [
        "/api/nginx/status",
        "/api/nginx/install",
        "/api/nginx/remove",
        "/api/nginx/config",
        "/api/nginx/validate",
        "/api/nginx/reload",
        "/api/nginx/logs",
        "/api/nginx/deploy",
        "/api/nginx/sites",
        "/api/nginx/sites/{host}",
        "/api/nginx/routes",
        "/api/nginx/instance/{action}",
    ],
    "frontend_tabs": ["sites", "instance"],
    "entry": [
        {"id": "sites", "title": "站点管理"},
        {"id": "instance", "title": "实例控制"},
    ],
    "plugins": [
        {"id": "sites", "title": "站点管理",
         "description": "站点增删改（反代/文件服务、TLS、下载路由开关）、nginx.conf 编辑"},
        {"id": "instance", "title": "实例控制",
         "description": "启动/停止/重启/重载、部署方式切换（实机/容器）、日志"},
    ],
}
