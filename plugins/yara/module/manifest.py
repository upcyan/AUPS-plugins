"""YARA 引擎插件清单（v1.0.0）：规则扫描引擎依赖插件。

- 引擎：YARA 二进制安装、扫描、规则订阅；
- 规则数据（rules/ 目录与订阅清单）由核心持有（aups.core.yara），
  本插件所有逻辑委托核心 yara 模块，保证规则数据唯一来源；
- 供核心主机安全（hostsec）与 cyansecengine（青·擎）调用；
- 提供能力 provides.yara，可被其它插件 depends 依赖。

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "yara",
    "title": "YARA 引擎",
    "version": "1.0.0",
    "description": "YARA 规则扫描引擎：引擎安装、规则订阅与扫描，规则数据由核心持有。供核心主机安全与 cyansecengine 调用",
    "type": "external",
    "attr": "依赖",
    "deploy": {"host": True},
    "config_dir": "yara",
    "data_dir": "yara",
    "cli_groups": ["yara"],
    "api_module": "aups.modules.yara.api",
    "api_paths": [
        "/api/yara/status",
        "/api/yara/install",
        "/api/yara/scan",
        "/api/yara/subscribe",
        "/api/yara/subscribe/sync",
    ],
    "frontend_tabs": ["yara"],
    "modules": ["scanner"],
    "provides": {"ids": "yara"},
    "entry": [
        {"id": "overview", "title": "引擎概览"},
        {"id": "rules", "title": "规则订阅"},
    ],
    "plugins": [
        {"id": "overview", "title": "引擎概览",
         "description": "YARA 引擎状态、安装与快速扫描"},
        {"id": "rules", "title": "规则订阅",
         "description": "在线 YARA 规则订阅与同步"},
    ],
}