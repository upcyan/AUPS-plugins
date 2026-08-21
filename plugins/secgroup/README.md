# 原生安全组

AUPS 的 `firewall` 能力 provider。使用 Linux nftables 建立独立的
`inet aups_secgroup` 表，不依赖 ufw/firewalld，也不会清空系统已有规则。

## 当前安全模型

- 默认放行，点击“关闭”时按端口、TCP/UDP 和来源 IP/CIDR 添加 drop 规则。
- 点击“放行”只删除本插件创建的对应 drop 规则。
- 规则持久化到插件配置数据块，面板服务启动或插件重新启用时自动恢复。
- 安装插件不会切换为默认拒绝，因此不会因缺少 SSH 放行规则而锁死服务器。
- 停用或卸载插件时删除专用表，不触碰其它 nftables 规则。

## 黑名单订阅

- 支持长亭 SafeLine 黑名单 JSON（`ip` 数组）、CrowdSec Blocklist Mirror 纯文本和 LAPI Decisions JSON。
- 也支持通用纯文本 IP/CIDR，以及 `data/items/rules/decisions` 嵌套 JSON。
- 多订阅结果自动校验、去重并合并连续网段，统一写入 IPv4/IPv6 nftables interval set。
- 支持 Bearer、X-Api-Key 和 Basic 认证；密钥以 `0600` 权限保存在本机，列表 API 不返回明文。
- 可为每个订阅设置更新周期，并通过 cron 定时检查到期订阅；同步失败时保留上次成功规则。

## 与 OpenGFW 类方案的边界

本插件负责 L3/L4 安全组。应用协议识别、域名/SNI/进程策略等 L7 能力适合后续
独立 NFQUEUE/eBPF 策略引擎插件，通过公共事件、规则数据块和 `firewall` API 联动，
不应与基础端口放行规则耦合。
