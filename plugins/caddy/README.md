# caddy — Caddy 环境

属性：环境

Caddy 反代：托管片段（下载路由/WAF）、WAF 防护、access 日志、Caddy 端口与防火墙。

负责 Caddy 反代/WAF 全部能力：反代抽象、Caddyfile 托管片段、WAF 防护、access 日志、Caddy 端口/防火墙。与 appupdate 解耦，可独立安装/启停。

## 功能

- **反代配置**：Caddy 后端状态、托管片段（下载路由/WAF）、端口与防火墙
- **WAF 防护**：规则增删改、IP 黑/白名单、限流、远程规则订阅
- **环境部署**：Caddy 状态与安装（部署二进制到面板目录）

## 面板页签

| 页签 | 说明 |
|---|---|
| 反代配置 | Caddy 后端状态、托管片段（下载路由/WAF）、端口与防火墙 |
| WAF 防护 | 规则增删改、IP 黑/白名单、限流、远程规则订阅 |

## CLI

```bash
aups caddy ...       # Caddy 状态与安装
aups caddyconf ...   # Caddy 配置管理
```

## 安装

```bash
aups plugins market install caddy
```

## 说明

作为反代环境插件，可为 appupdate 等应用提供下载路由托管片段。若需证书签发，可搭配 certbot / acme 依赖插件使用。
