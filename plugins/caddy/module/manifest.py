"""caddy 插件清单：Caddy 环境插件（属性=环境）。

负责 Caddy 反代/WAF 全部能力：反代抽象、Caddyfile 托管片段、WAF 防护、
access 日志、Caddy 端口/防火墙。与 appupdate 解耦，可独立安装/启停。
"""

MANIFEST = {
    "name": "caddy",
    "title": "Caddy 环境",
    "version": "1.0.0",
    "description": "Caddy 反代：托管片段（下载路由/WAF）、WAF 防护、access 日志、Caddy 端口与防火墙",
    "type": "external",
    "attr": "环境",
    "proxy": "caddy",
    "rproxy_module": "aups.modules.caddy.rproxy.caddy",
    "config_dir": "caddy",
    "data_dir": "caddy",
    "cli_groups": ["caddyconf", "caddy"],
    "api_module": "aups.modules.caddy.api",
    "api_paths": [
        "/api/caddy/status",
        "/api/caddy/install",
        "/api/caddyconf",
        "/api/caddyconf/status",
        "/api/caddyconf/show",
        "/api/caddyconf/preview",
        "/api/caddyconf/apply",
        "/api/caddyconf/waf",
        "/api/caddyconf/waf/rules",
        "/api/caddyconf/waf/ips",
        "/api/caddyconf/waf/ratelimit",
        "/api/caddyconf/waf/subscribe",
        "/api/stats/accesslog",
        "/api/ports/caddy",
        "/api/apps/caddy",
    ],
    "frontend_tabs": ["caddy-rproxy", "security-waf"],
    "modules": ["waf", "rproxy", "env"],
    "plugins": [
        {"id": "rproxy", "title": "反代配置",
         "description": "Caddy 后端状态、托管片段（下载路由/WAF）、端口与防火墙"},
        {"id": "waf", "title": "WAF 防护",
         "description": "规则增删改、IP 黑/白名单、限流、远程规则订阅"},
        {"id": "env", "title": "环境部署",
         "description": "Caddy 状态与安装（部署二进制到面板目录）"},
    ],
}
