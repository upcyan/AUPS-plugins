# CyanSecEngine · 安全加固

轻量主机安全加固插件（Phase 1+2）。所有引擎均为**按需扫描**，无常驻进程，适配小内存 VPS。

## 引擎

| 引擎 | 作用 | 内存占用 | 备注 |
|------|------|---------|------|
| rkhunter | rootkit / 后门 / 基线偏离检测 | 扫描时才占用 | 按需 `--check` |
| LMD (maldet) | 恶意文件 / Webshell 扫描 | 扫描时才占用 | 带隔离区 quarantine |
| YARA | 自定义 / 订阅规则匹配 | <10MB | 规则可在线订阅 |

## 安装

插件市场安装 `cyansecengine` 后：

1. 进入「安全加固 → 安全概览」，一键安装所需引擎（rkhunter / LMD / YARA）
2. 可选：在「规则订阅」添加 YARA 规则源并同步（默认内置 signature-base）

## 使用

### 扫描

- rkhunter：`aups plugins cyansecengine sec scan rkhunter`
- LMD：`aups plugins cyansecengine sec scan lmd [/path ...]`
- YARA：`aups plugins cyansecengine sec scan yara [/path ...]`

扫描结果自动保存为报告：`aups plugins cyansecengine sec reports`

### 规则订阅

```bash
aups plugins cyansecengine sec subscribe                  # 查看订阅
aups plugins cyansecengine sec sub-add <URL> --name 名称  # 添加订阅
aups plugins cyansecengine sec sub-sync --due             # 仅同步到期订阅（cron 用）
```

订阅的规则文件下载到 `PANEL_DATA_DIR/cyansecengine/rules/`。

### 隔离区

```bash
aups plugins cyansecengine sec quarantine   # 列出隔离文件
aups plugins cyansecengine sec restore <名称>
```

## 数据目录

- 配置/数据：`PANEL_DATA_DIR/cyansecengine/`
- 订阅清单：`data/cyansecengine/subscribe.json`
- 扫描报告：`data/cyansecengine/reports/*.json`
- YARA 规则：`data/cyansecengine/rules/*.yar`

## 说明

- 与核心 WAF 模板互补：WAF 管流量层，本插件管主机层（rootkit / 恶意文件 / Webshell）。
- 默认扫描路径：面板数据目录 + `/tmp` + `/var/tmp`；可指定任意路径。
- LMD 检测到恶意文件默认移入隔离区，可在「隔离区」页查看/恢复。
