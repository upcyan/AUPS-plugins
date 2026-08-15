# cyansecengine — 青·擎（占位壳）

属性：功能

青·擎（原安全加固）。v3.0.0 起为保留占位壳：主机安全（rkhunter/LMD）为 rkhunter / lmd 依赖插件、实时防护（fanotify）与 YARA 引擎已并入面板核心与 yara 依赖插件。

## 能力迁移

| 能力 | 新位置 |
|---|---|
| 主机安全（rkhunter / LMD 扫描、隔离区） | 面板 → 安全管理 → 安全加固 → 安全引擎（配合 rkhunter / lmd 依赖插件） |
| 实时防护（fanotify + YARA + WAF 联动） | 面板 → 安全管理 → 安全加固 → 实时防护 |
| YARA 引擎与规则订阅 | 插件中心 → YARA 引擎 |
| CLI `aups sec ...` | `aups hostsec ...` / `aups rtguard ...` |

## 说明

- 数据未迁移（按设计直接新建），新数据目录：`/opt/aups/data/yara/`、`/opt/aups/data/hostsec/`、`/opt/aups/data/rtguard/`。
- 本插件不含任何运行逻辑，可安全卸载（不影响核心功能）。
- 卸载只清理部署的软件（若曾由本插件安装过 rkhunter/LMD/yara 二进制），保留数据目录（保数据卸载）。