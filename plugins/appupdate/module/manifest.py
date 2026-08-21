"""appupdate 模块清单：多应用管理、部署配置、版本管理、CI 用户。

CLI 命令组在 aups/core/cli.py 中按此清单注册；Web 路由在 aups/web/app.py 中按此挂载。
"""

MANIFEST = {
    "name": "appupdate",
    "title": "应用更新管理",
    "version": "2.3.2",
    "description": "多应用管理：部署配置（域名/SSL/端口/用户）、版本管理、CI 上传、存储配额、下载统计",
    "type": "external",
    "attr": "功能",
    "depends": [{"capability": "proxy"}],
    "exports": {
        "version": "1",
        "api": [{
            "id": "download_routes", "module": "apps", "function": "public_download_routes",
            "callers": ["caddy"],
        }],
        "data": [{
            "id": "download_routes", "readers": ["caddy"],
            "schema": {
                "type": "object", "required": ["apps"],
                "properties": {"apps": {"type": "array", "items": {
                    "type": "object", "required": ["name", "versions"],
                    "properties": {"name": {"type": "string"}, "versions": {"type": "array"}},
                }}},
            },
        }],
    },
    "cli_groups": ["app", "storage", "user", "ssh"],
    "api_module": "aups.modules.appupdate.api",
    "api_paths": [
        "/api/apps",
        "/api/apps/{name}",
        "/api/apps/{name}/versions",
        "/api/apps/{name}/versions/{version}/lock",
        "/api/apps/{name}/versions/{version}/unlock",
        "/api/apps/{name}/quota",
        "/api/apps/{name}/deploy",
        "/api/apps/{name}/deploy/domain",
        "/api/apps/{name}/deploy/ssl",
        "/api/apps/{name}/deploy/port",
        "/api/apps/{name}/deploy/workdir",
        "/api/apps/{name}/deploy/user",
        "/api/apps/{name}/deploy/sshkey",
        "/api/apps/caddy",
        "/api/apps/discover",
        "/api/storage/usage",
        "/api/storage/apks",
        "/api/storage/quota",
        "/api/storage/enforce",
        "/api/storage/delete",
        "/api/stats/downloads",
        "/api/users",
        "/api/users/{name}",
        "/api/users/{name}/dirs",
        "/api/users/{name}/dirs/remove",
        "/api/ssh/{user}",
        "/api/ssh/{user}/{index}",
    ],
    "frontend_tabs": ["apps", "users", "storage"],
    "entry": [
        {"id": "apps", "title": "应用管理"},
        {"id": "users", "title": "CI 用户"},
        {"id": "storage", "title": "存储管理"},
    ],
    "plugins": [
        {"id": "apps", "title": "应用管理",
         "description": "应用注册、部署配置（域名/SSL/端口/用户）、版本管理、反代路由"},
        {"id": "users", "title": "CI 用户",
         "description": "系统用户创建、SSH 公钥管理、目录 ACL 授权"},
        {"id": "storage", "title": "存储管理",
         "description": "磁盘用量、配额设置、版本清理"},
    ],
    "cards": [
        {"id": "downloads", "title": "下载统计",
         "min_w": 1, "max_w": 3, "default_w": 2, "min_h": 1, "max_h": 2, "default_h": 1},
        {"id": "appsoverview", "title": "应用概览",
         "min_w": 1, "max_w": 3, "default_w": 1, "min_h": 1, "max_h": 2, "default_h": 1},
    ],
}
