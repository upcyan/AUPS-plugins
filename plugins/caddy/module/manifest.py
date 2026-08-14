"""caddy 插件清单（v1.0.1）：Caddy 环境插件（属性：环境）。

负责 Caddy 反代全部能力：反代抽象（托管片段）、WAF 模板渲染（规则来自核心
aups.core.waf，本插件实现 Caddy 语法转换器）、access 日志、Caddy 端口/防火墙。
WAF 规则模板已提升到核心（安全页「WAF 模板」），本插件不再自带规则库。
与 appupdate 解耦：下载路由数据由 appupdate 提供（公共数据），本插件负责
把路由/规则渲染成 Caddyfile（领域职责），不依赖 appupdate 内部实现。
"""

MANIFEST = {
    "name": "caddy",
    "title": "Caddy 环境",
    "version": "1.0.1",
    "description": "Caddy 反代：托管片段（下载路由/WAF 模板转换）、access 日志、Caddy 端口与防火墙",
    "type": "external",
    "attr": "环境",
    # 反代能力声明：本插件是 proxy 能力提供者
    "provides": {"proxy": "caddy"},
    "proxy": "caddy",
    "rproxy_module": "aups.modules.caddy.rproxy.caddy",
    # 反代能力集（rproxy 能力协商用）：声明本反代支持哪些能力
    "capabilities": ["status", "show", "preview", "apply", "reload",
                     "waf", "download_route", "access_log", "port"],
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
        "/api/caddyconf/waf",           # 兼容旧接口：代理核心 WAF
        "/api/caddyconf/waf/rules",
        "/api/caddyconf/waf/rules/{rule_id}",
        "/api/caddyconf/waf/rules/{rule_id}/toggle",
        "/api/caddyconf/waf/ips",
        "/api/caddyconf/waf/ratelimit",
        "/api/caddyconf/waf/subscribe",
        "/api/caddyconf/waf/subscribe/recommended",
        "/api/stats/accesslog",
        "/api/ports/caddy",
    ],
    "frontend_tabs": ["caddy-rproxy"],
    "plugins": [
        {"id": "rproxy", "title": "反代配置",
         "description": "Caddy 后端状态、托管片段（下载路由/WAF 转换）、端口与防火墙"},
        {"id": "env", "title": "环境部署",
         "description": "Caddy 状态与安装（部署二进制到面板目录）"},
    ],
}
