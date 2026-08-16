"""cyansecengine（青·擎）模块清单（v3.0.0）：占位壳。

v1 时代的安全加固能力已并入面板核心：
- rkhunter / LMD 扫描 → 核心主机安全（安全管理页「主机安全」子页）
- fanotify 实时防护 → 核心实时防护（安全管理页「实时防护」子页）
- YARA 引擎 → 独立依赖插件（市场 plugins/yara），规则数据由核心持有
- CLI `aups sec ...` → 已并入核心 `aups hostsec / aups rtguard`

本插件保留为空壳（无 api_module / modules / cli_groups），
前端提供迁移提示页。为兼容历史安装，仍保留 name/attr 字段。

部署方式：实机（host）。
"""

MANIFEST = {
    "name": "cyansecengine",
    "title": "青·擎",
    "version": "3.0.0",
    "description": "青·擎（原安全加固）。主机安全（rkhunter/LMD）、实时防护与 YARA 引擎已并入面板核心与 yara 依赖插件，本插件为保留占位壳",
    "type": "external",
    "attr": "功能",
    "deploy": {"host": True},
    "config_dir": "cyansecengine",
    "data_dir": "cyansecengine",
    "entry": [
        {"id": "migrated", "title": "迁移指引"},
    ],
    "plugins": [
        {"id": "migrated", "title": "青·擎",
         "description": "功能已迁移至核心，本页为迁移指引"},
    ],
}
