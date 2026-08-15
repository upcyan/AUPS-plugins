"""cyansecengine 模块清单（v0.1.0）：安全加固。

- 扫描器：rkhunter（rootkit/入侵检测）、LMD/maldet（恶意文件）、YARA（自定义/订阅规则）
- 在线规则订阅：支持订阅远程 YARA 规则仓库（默认 signature-base）定时同步
- 与核心能力互补：WAF 模板（流量层）在核心，本插件专注主机层加固

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "cyansecengine",
    "title": "安全加固",
    "version": "0.1.0",
    "description": "轻量主机安全加固：rkhunter 入侵检测、LMD 恶意软件扫描、YARA 规则订阅、Webshell 排查",
    "type": "external",
    "attr": "功能",
    "deploy": {"host": True},
    "config_dir": "cyansecengine",
    "data_dir": "cyansecengine",
    "cli_groups": ["sec"],
    "api_module": "aups.modules.cyansecengine.api",
    "api_paths": [
        "/api/cyansec/status",
        "/api/cyansec/install",
        "/api/cyansec/scan",
        "/api/cyansec/reports",
        "/api/cyansec/reports/{rid}",
        "/api/cyansec/quarantine",
        "/api/cyansec/quarantine/restore",
        "/api/cyansec/subscribe",
        "/api/cyansec/subscribe/sync",
    ],
    "frontend_tabs": ["cyansec"],
    "modules": ["scanner", "subscribe"],
    "plugins": [
        {"id": "overview", "title": "安全概览",
         "description": "引擎状态、一键安装、快速扫描入口"},
        {"id": "scan", "title": "扫描",
         "description": "rkhunter / LMD / YARA 扫描与报告"},
        {"id": "quarantine", "title": "隔离区",
         "description": "LMD 隔离文件查看与恢复"},
        {"id": "rules", "title": "规则订阅",
         "description": "在线 YARA 规则订阅与同步"},
    ],
}
