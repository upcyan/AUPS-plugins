# baseline — VPS 基线检查

纯只读审计插件：不部署软件、不改任何系统配置。一键巡检四类基线并生成报告（报告复用核心 `aups.core.hostsec` 数据层）。

## 检查项

| 类别 | 检查项 |
|---|---|
| 账号与权限 | UID 0 账号、空密码账号、可登录 shell 账号、sudoers 免密/提权规则、敏感文件权限（passwd/shadow/sudoers/sshd_config）、SUID/SGID 文件 |
| 系统配置基线 | 密码策略（login.defs）、SSH 加固（PermitRootLogin/PasswordAuth/X11）、fail2ban、系统待更新包、自动安全更新 |
| 内核与网络加固 | sysctl 内核参数（ip_forward/重定向/源路由/syncookies/rp_filter）、防火墙状态 |
| 服务与应用基线 | 公网监听端口、安全组件覆盖（WAF/实时防护/安全引擎/权限代理） |

每项返回 `{id, group, title, ok, current, expected, advice, critical}`，汇总写入共享报告目录（`tool=baseline`）。

## 架构

- `module/scanner.py`：检查项实现（纯只读，按发行版适配包管理器）
- `module/api.py`：`/api/baseline/status|check|reports|report/{rid}`
- 报告数据层委托核心 `aups.core.hostsec`（`save_report/reports/report`），与 rkhunter/lmd 报告同库展示
- 核心「安全加固」页新增「基线检查」子页聚合调用

## 使用

- 面板 → 安全管理 → 安全加固 → 基线检查 → 「运行基线检查」
- 或插件中心 → baseline → 「基线巡检」
- 报告可查看每项当前值 / 期望值 / 处置建议

## 说明

- 需 root 读取 `/etc/shadow`、`/proc/sys` 等；非 Linux 环境检查项自动跳过（不报错）。
- `check()` 全部只读：`find`（SUID）/ 包管理器查询均带超时，不会触发任何写入。