"""baseline 模块清单（v1.0.0）：VPS 基线检查功能插件。

- 纯只读审计：不部署软件、不改系统配置；
- 检查项（账号/系统配置/内核网络/服务应用四类）由本插件实现（scanner.py）；
- 报告数据层委托核心 aups.core.hostsec（save_report/reports/report）；
- 提供能力 provides.baseline，供核心「安全加固」页调用；
- 安装（market install / 更新）无需部署，无 post_install/remove 资源清理。

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "baseline",
    "title": "基线检查",
    "version": "1.0.0",
    "description": "VPS 基线检查（纯只读审计）：账号与权限 / 系统配置 / 内核网络加固 / 服务应用，四类检查项一键巡检并生成报告",
    "type": "external",
    "attr": "功能",
    "deploy": {"host": True},
    "config_dir": "hostsec",
    "data_dir": "hostsec",
    "api_module": "aups.modules.baseline.api",
    "api_paths": [
        "/api/baseline/status",
        "/api/baseline/check",
        "/api/baseline/reports",
        "/api/baseline/report/{rid}",
    ],
    "modules": ["scanner"],
    "provides": {"baseline": "baseline"},
    "plugins": [
        {"id": "overview", "title": "基线巡检",
         "description": "账号、系统配置、内核网络、服务应用四类基线检查"},
    ],
}