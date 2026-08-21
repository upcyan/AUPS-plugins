"""caddy 插件清单（v1.2.0）：Caddy 依赖插件（属性：依赖）。

负责 Caddy 反代全部能力：反代抽象（托管片段）、WAF 模板渲染（规则来自核心
aups.core.waf，本插件实现 Caddy 语法转换器）、access 日志、Caddy 防火墙。
WAF 规则模板已提升到核心（安全页「WAF 模板」），本插件不再自带规则库。
与 appupdate 解耦：下载路由数据由 appupdate 提供（公共数据），本插件负责
把路由/规则渲染成 Caddyfile（领域职责），不依赖 appupdate 内部实现。
v1.1.0：支持容器部署（docker/podman）；新增 Caddyfile 管理（全文件读写 +
站点块增删改 + 常用片段预设）与实例控制（stop/restart/reload）。
v1.1.1：移除「Caddy HTTPS 端口」功能；Caddyfile 缺失时优雅返回空内容；
各页容错渲染，避免加载失败卡在占位页。
v1.2.0：移除反代配置页；实例控制新增实时状态与日志显示。
"""

MANIFEST = {
    "name": "caddy",
    "title": "Caddy 依赖",
    "version": "1.3.7",
    "description": "Caddy 反代：Caddyfile 管理、实例控制、access 日志、防火墙",
    "type": "external",
    "attr": "依赖",
    # 反代能力声明：本插件是 proxy 能力提供者
    "provides": {"proxy": "caddy"},
    "proxy": "caddy",
    "rproxy_module": "aups.modules.caddy.rproxy.caddy",
    # 反代能力集（rproxy 能力协商用）：声明本反代支持哪些能力
    "capabilities": ["status", "show", "preview", "apply", "reload",
                     "waf", "download_route", "access_log"],
    # 部署方式：实机 + 容器（docker/podman）
    "deploy": {"host": True, "container": {"kinds": ["docker", "podman"]}},
    "config_dir": "caddy",
    "data_dir": "caddy",
    "cli_groups": ["caddyconf", "caddy"],
    "api_module": "aups.modules.caddy.api",
    "api_paths": [
        "/api/caddy/status",
        "/api/caddy/install",
        "/api/caddy/instance/reload",
        "/api/caddy/instance/stop",
        "/api/caddy/instance/start",
        "/api/caddy/instance/restart",
        "/api/caddy/caddyfile",
        "/api/caddy/sites",
        "/api/caddy/sites/{host}",
        "/api/caddy/presets",
        "/api/caddy/journal",
        "/api/caddyconf",               # 保留：供其他插件/核心调用
        "/api/caddyconf/status",
        "/api/caddyconf/waf",           # 兼容旧接口：代理核心 WAF
        "/api/caddyconf/waf/rules",
        "/api/caddyconf/waf/rules/{rule_id}",
        "/api/caddyconf/waf/rules/{rule_id}/toggle",
        "/api/caddyconf/waf/ips",
        "/api/caddyconf/waf/ratelimit",
        "/api/caddyconf/waf/subscribe",
        "/api/caddyconf/waf/subscribe/recommended",
        "/api/stats/accesslog",
    ],
    "frontend_tabs": ["caddyfile", "instance"],
    "entry": [
        {"id": "caddyfile", "title": "Caddyfile 管理"},
        {"id": "instance", "title": "实例控制"},
    ],
    "plugins": [
        {"id": "caddyfile", "title": "Caddyfile 管理",
         "description": "全文件读写、站点块增删改、常用片段预设（参考 caddydash）"},
        {"id": "instance", "title": "实例控制",
         "description": "停止 / 重启 / 重载 Caddy 服务（容器与实机部署通用）"},
    ],
}
