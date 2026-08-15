"""漏洞检测模块清单（v1.0.0）：系统与部署软件漏洞检测功能插件。

- 检测：系统待安全更新/待更新包、是否需重启、自动安全更新；部署软件
  （nginx/caddy/certbot/acme.sh/rkhunter/maldet/yara/fail2ban/openssl/curl/redis）
  版本与源仓库候选版本比对；
- 修复：一键安装安全补丁 / 升级指定软件（依赖系统包管理器，需 root）；
- 报告数据层委托核心 aups.core.hostsec（save_report/reports/report）；
- 提供能力 provides.vuln，供核心「安全加固 → 漏洞检测」页调用；
- 安装（market install / 更新）无需部署，无 post_install/remove 资源清理。

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "vuln",
    "title": "漏洞检测",
    "version": "1.0.0",
    "description": "系统与部署软件漏洞检测：待安全更新/补丁、部署软件版本比对，检测到漏洞提示解决方案并可一键修复（装补丁/升级）",
    "type": "external",
    "attr": "功能",
    "deploy": {"host": True},
    "config_dir": "hostsec",
    "data_dir": "hostsec",
    "api_module": "aups.modules.vuln.api",
    "api_paths": [
        "/api/vuln/status",
        "/api/vuln/check",
        "/api/vuln/fix",
        "/api/vuln/reports",
        "/api/vuln/report/{rid}",
    ],
    "modules": ["scanner"],
    "provides": {"vuln": "vuln"},
    "plugins": [
        {"id": "overview", "title": "漏洞检测",
         "description": "系统安全更新与部署软件漏洞检测，一键修复"},
    ],
}