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
    "cli_groups": ["caddyconf"],
    "api_module": "aups.modules.caddy.api",
    "api_paths": [
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
        "/api/ports",
        "/api/ports/caddy",
        "/api/apps/caddy",
    ],
    "frontend_tabs": ["caddy-rproxy", "security-waf"],
    "modules": ["waf", "rproxy"],
    "plugins": [
        {"id": "rproxy", "title": "反代配置",
         "description": "Caddy 后端状态、托管片段（下载路由/WAF）、端口与防火墙"},
        {"id": "waf", "title": "WAF 防护",
         "description": "规则增删改、IP 黑/白名单、限流、远程规则订阅"},
    ],
}
