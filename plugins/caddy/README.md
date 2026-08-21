# caddy — Caddy 环境

属性：依赖

Caddy 反代：托管片段（下载路由/WAF）、WAF 防护、Caddyfile 管理、实例控制、access 日志、Caddy 端口与防火墙。

负责 Caddy 反代/WAF 全部能力：反代抽象、Caddyfile 托管片段、WAF 防护、Caddyfile 管理（参考 caddydash）、实例控制、access 日志、Caddy 端口/防火墙。与 appupdate 解耦，可独立安装/启停。支持实机与容器（docker/podman）两种部署方式。

## 功能

- **反代配置**：Caddy 后端状态、托管片段（下载路由/WAF）、端口与防火墙
- **WAF 防护**：规则增删改、IP 黑/白名单、限流、远程规则订阅
- **Caddyfile 管理**（参考 [caddydash](https://github.com/WJQSERVER-STUDIO/caddydash)）：
  完整 Caddyfile 读写、站点块增删改（反向代理 / 文件服务两种模式）、常用片段预设
- **实例控制**：停止 / 重启 / 重载 Caddy 服务（实机 systemd/二进制、容器运行时通用）
- **环境部署**：Caddy 状态与安装（实机二进制到面板目录，或容器部署）

## 部署方式

安装时可选 **实机** 或 **容器** 部署：

- **实机**：复制 caddy 二进制到面板 runtime 目录，切换 systemd 单元指向面板配置
- **容器**：以 `caddy:2` 官方镜像运行容器（docker/podman），使用 host 网络保持
  `127.0.0.1:应用端口` 反代兼容；持久化挂载 `/etc/caddy`、`/data`、`/config`
  与 `/var/log/caddy`，并只读挂载应用默认目录以兼容下载文件服务；实例控制和日志读取
  均自动切换到容器运行时

## 面板页签

| 页签 | 说明 |
|---|---|
| 反代配置 | Caddy 后端状态、托管片段（下载路由/WAF）、端口与防火墙 |
| Caddyfile 管理 | 全文件读写、站点块增删改、常用片段预设 |
| 实例控制 | 停止 / 重启 / 重载 Caddy 服务 |

## CLI

```bash
aups caddy ...                # Caddy 状态 / 安装 / 实例控制 / Caddyfile 管理
aups caddy instance reload    # 重载 Caddy
aups caddy caddyfile show     # 显示完整 Caddyfile
aups caddy caddyfile sites    # 列出站点块
aups caddy caddyfile add <host> --mode reverse_proxy --target localhost:8080
aups caddyconf ...            # Caddy 配置管理（反代/WAF）
```

## 安装

```bash
aups plugins market install caddy            # 实机（默认）
aups plugins market install caddy --deploy container   # 容器部署
```

## 说明

作为反代环境插件，可为 appupdate 等应用提供下载路由托管片段。若需证书签发，可搭配 certbot / acme 依赖插件使用。容器部署要求服务器已安装 docker 或 podman 运行时（可在「容器」页安装）。
