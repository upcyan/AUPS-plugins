"""青·擎统一安全编排模块清单。"""

MANIFEST = {
    "name": "cyansecengine",
    "title": "青·擎",
    "version": "3.1.0",
    "description": "青·擎统一安全编排：防火墙、WAF、漏洞检测、主机安全和实时防护的统一状态与操作入口",
    "type": "external",
    "attr": ["安全", "网络"],
    "deploy": {"host": True},
    "config_dir": "cyansecengine",
    "data_dir": "cyansecengine",
    "depends": [
        {"name": "secgroup"},
        {"name": "vuln", "optional": True},
        {"name": "rkhunter", "optional": True},
        {"name": "lmd", "optional": True},
        {"name": "yara", "optional": True},
    ],
    "api_module": "aups.modules.cyansecengine.api",
    "api_paths": [
        "/api/cyansecengine/status",
        "/api/cyansecengine/check",
        "/api/cyansecengine/waf",
        "/api/cyansecengine/realtime",
        "/api/cyansecengine/firewall/open",
        "/api/cyansecengine/firewall/close",
    ],
    "modules": ["api", "firewall", "security"],
    "provides": {"firewall": "cyansecengine"},
    "priority": 100,
    "exports": {
        "version": "1",
        "api": [
            {"id": "status", "module": "security", "function": "status"},
            {"id": "check", "module": "security", "function": "check"},
            {"id": "waf_update", "module": "security", "function": "waf_update"},
            {"id": "realtime_update", "module": "security", "function": "realtime_update"},
        ],
    },
    "entry": [
        {"id": "overview", "title": "安全总览"},
    ],
    "plugins": [
        {"id": "overview", "title": "安全总览",
         "description": "统一查看并进入防火墙、WAF、漏洞检测、主机安全和实时防护"},
    ],
}
