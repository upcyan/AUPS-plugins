# CyanSecEngine · 安全加固

轻量主机安全加固插件。所有引擎均为**按需扫描或极低常驻开销**，适配小内存 VPS。

## 引擎

| 引擎 | 作用 | 内存占用 | 备注 |
|------|------|---------|------|
| rkhunter | rootkit / 后门 / 基线偏离检测 | 扫描时才占用 | 按需 `--check` |
| LMD (maldet) | 恶意文件 / Webshell 扫描 | 扫描时才占用 | 带隔离区 quarantine |
| YARA | 自定义 / 订阅规则匹配 | <10MB | 规则可在线订阅 |
| 实时防护 (fanotify) | 文件写入/创建实时监听 | <20MB 守护进程 | 命中 YARA 即处置，可选 WAF 联动 |

## 实时防护（Phase 3）

`fanotify`（Linux 内核 API）监听配置目录树内的写入/创建/移动事件，命中文件自动跑
YARA 规则（复用订阅的规则）。命中后：

1. 记录告警（`data/cyansecengine/rt_events.json`）
2. **主动防御联动核心 WAF**：为核心 WAF 添加 `path_regex` 拦截规则，`waf.on_change`
   自动通知支持 waf 能力的反代（如 caddy）reload，即刻封堵访问
3. 可选：把命中文件移入隔离目录

fanotify 不可用（内核/权限）时自动回退为**轮询扫描**（间隔可配，默认 5s）。

```bash
aups plugins cyansecengine sec rt                 # 状态
aups plugins cyansecengine sec rt-on /path ...    # 开启（可加 --no-quarantine / --no-waf / --interval）
aups plugins cyansecengine sec rt-off             # 关闭
aups plugins cyansecengine sec rt-events          # 告警记录
```

## 安装

插件市场安装 `cyansecengine` 后：

1. 进入「安全加固 → 安全概览」，一键安装所需引擎（rkhunter / LMD / YARA）
2. 可选：在「规则订阅」添加 YARA 规则源并同步（默认内置 signature-base）
3. 可选：在「实时防护」开启 fanotify 监听 + WAF 联动

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
- 实时防护：`data/cyansecengine/rt.conf` / `rt_events.json` / `quarantine/`

## 说明

- 与核心 WAF 模板互补：WAF 管流量层，本插件管主机层（rootkit / 恶意文件 / Webshell）。
- 默认扫描路径：面板数据目录 + `/tmp` + `/var/tmp`；可指定任意路径。
- LMD 检测到恶意文件默认移入隔离区，可在「隔离区」页查看/恢复。
- 实时防护需 root；主动防御联动 WAF 需核心已安装且支持 waf 能力的反代（caddy）。
