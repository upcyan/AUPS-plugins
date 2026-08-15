# yara — YARA 引擎

属性：依赖

YARA 规则扫描引擎：引擎安装、规则订阅与扫描。规则数据（rules/ 目录与订阅清单）由核心持有（`aups.core.yara`），本插件提供 HTTP API 与前端入口，供核心主机安全（hostsec）与 cyansecengine（青·擎）调用。

## 功能

- **引擎管理**：YARA 二进制状态检查与系统包管理器安装
- **扫描**：用本地规则库多路径递归扫描，命中记录进报告
- **规则订阅**：订阅远程 YARA 规则库（默认 signature-base 精选规则）定时同步

## 面板页签

| 页签 | 说明 |
|---|---|
| 引擎概览 | YARA 引擎状态、安装与快速扫描 |
| 规则订阅 | 在线 YARA 规则订阅与同步 |

## CLI

```bash
aups yara status
aups yara install
aups yara scan [路径...]
aups yara subscribe [--add URL] [--remove URL]
aups yara subscribe sync
```

## 安装

```bash
aups plugins market install yara
```

## 说明

- 规则目录与订阅数据位于 `/opt/aups/data/yara/`（核心持有，不随插件卸载而删除）。
- 核心实时防护（rtguard）直接读取规则目录，无需安装本插件即生效。