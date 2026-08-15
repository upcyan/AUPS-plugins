"""lmd 模块清单（v1.0.0）：LMD (maldet) 恶意软件扫描引擎依赖插件。

- 引擎安装/卸载/扫描/报告/隔离区逻辑由核心持有（aups.core.hostsec），本插件委托核心；
- 提供能力 provides.lmd，供核心「安全引擎」按需调用；
- 安装（market install / 更新）时执行 post_install()：若已存在旧二进制，
  先卸载再重装为插件受管（强制统一通过插件重装）。

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "lmd",
    "title": "LMD",
    "version": "1.0.0",
    "description": "LMD (maldet) 恶意软件扫描引擎（依赖插件）：由核心安全引擎按需调用，扫描/报告/隔离区，安装时若已存在旧二进制将先卸载再重装为插件受管",
    "type": "external",
    "attr": "依赖",
    "deploy": {"host": True},
    "config_dir": "hostsec",
    "data_dir": "hostsec",
    "api_module": "aups.modules.lmd.api",
    "api_paths": [
        "/api/lmd/status",
        "/api/lmd/install",
        "/api/lmd/reinstall",
        "/api/lmd/uninstall",
        "/api/lmd/scan",
        "/api/lmd/report",
        "/api/lmd/reports",
        "/api/lmd/quarantine",
        "/api/lmd/quarantine/restore",
    ],
    "modules": ["scanner"],
    "provides": {"lmd": "lmd"},
    "plugins": [
        {"id": "overview", "title": "LMD",
         "description": "LMD 状态 / 安装 / 重装 / 卸载"},
        {"id": "quarantine", "title": "隔离区",
         "description": "LMD 隔离文件查看与恢复"},
    ],
}