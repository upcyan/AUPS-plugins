"""rkhunter 模块清单（v1.0.0）：主机入侵检测引擎依赖插件。

- 引擎安装/卸载/扫描/报告逻辑由核心持有（aups.core.hostsec），本插件委托核心；
- 提供能力 provides.rkhunter，供核心「安全引擎」按需调用；
- 安装（market install / 更新）时执行 post_install()：若二进制已以旧方式存在，
  先卸载再重装为插件受管（强制统一通过插件重装）。

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "rkhunter",
    "title": "rkhunter",
    "version": "1.0.0",
    "description": "rkhunter 主机入侵检测引擎（依赖插件）：由核心安全引擎按需调用，安装时若已存在旧二进制将先卸载再重装为插件受管",
    "type": "external",
    "attr": "依赖",
    "deploy": {"host": True},
    "config_dir": "hostsec",
    "data_dir": "hostsec",
    "api_module": "aups.modules.rkhunter.api",
    "api_paths": [
        "/api/rkhunter/status",
        "/api/rkhunter/install",
        "/api/rkhunter/reinstall",
        "/api/rkhunter/uninstall",
        "/api/rkhunter/scan",
        "/api/rkhunter/report",
        "/api/rkhunter/reports",
    ],
    "modules": ["scanner"],
    "provides": {"rkhunter": "rkhunter"},
    "plugins": [
        {"id": "overview", "title": "rkhunter",
         "description": "rkhunter 状态 / 安装 / 重装 / 卸载"},
    ],
}