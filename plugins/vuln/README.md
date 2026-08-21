# vuln — 漏洞检测

系统与部署软件漏洞检测插件：只读扫描 + 一键修复（装补丁 / 升级软件）。报告复用核心 `aups.core.hostsec` 数据层。

## 检测项

| 类别 | 检测项 |
|---|---|
| 系统漏洞 | 待安全更新/补丁数量、全部待更新包数量、是否需要重启系统、自动安全更新是否启用 |
| 部署的软件漏洞 | nginx / Caddy / certbot / acme.sh / rkhunter / LMD / YARA / fail2ban / OpenSSL / curl / Redis 版本与源仓库候选版本比对 |

每项返回 `{id, group, title, ok, current, expected, advice, critical, fixable, fix_scope, pkg}`。`ok=False 且 fixable=True` 的项前端按 `fix_scope` 调用正确的修复方式：

- **安全更新**：仅安装安全通道补丁（`apt-get install --only-upgrade` 安全包 / `dnf upgrade --security` / `yum update --security` / `zypper patch`），避免全量升级引入兼容风险；
- **升级指定软件**：按包管理器升级单个软件（`pkg`）；
- **全部修复**：整体升级全部待更新包。

## 架构

- `module/scanner.py`：检测与修复实现（跨发行版适配 apt/dnf/yum/apk/zypper/pacman）
- `module/api.py`：`/api/vuln/status|check|fix|reports|report/{rid}`
- 报告数据层委托核心 `aups.core.hostsec`（`save_report/reports/report`），与基线检查/扫描报告同库展示
- 核心「安全加固 → 漏洞检测」子页聚合调用

## 使用

- 面板 → 安全管理 → 安全加固 → 漏洞检测 → 「运行漏洞检测」，检测到可修复项点「修复」/「一键修复全部」
- 或插件中心 → vuln → 「漏洞检测」

## 说明

- 检测为纯只读（`apt-get -s` / `apt-cache policy` / `dnf check-update` / `apk list` 等带超时）；
- 修复需要 root 权限并可能调用系统包管理器联网下载补丁，执行前请在界面确认；
- 非包管理器来源软件（如 acme.sh、LMD 脚本安装）仅提示手动核对，不强制修复。
