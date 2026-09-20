# nginx — Nginx 环境

属性：依赖

Nginx 反代：托管片段（下载路由/WAF）、站点管理、实例控制，UI 与 caddy 插件对齐。与 appupdate 解耦，可独立安装/启停。支持实机与容器（docker/podman）两种部署方式。

## 功能

- **站点管理**：站点增删改（反向代理/文件服务、TLS 证书、WebSocket、下载路由开关）、nginx.conf 完整编辑（保存前校验，失败自动恢复）、常用片段预设
- **托管下载路由**（`download_route` 能力，与 caddy 后端对齐）：文件服务站点开启「下载路由」后，自动把 appupdate 的版本短链与 latest 重定向（按文件日期）渲染为 `aups-routes.conf` 并 include 进该站点；apply 前实时重取数据，无变化跳过 reload
- **WAF 防护**：规则增删改、IP 黑/白名单、限流（随站点渲染进 aups-sites.conf）
- **实例控制**：启动/停止/重启/重载、部署方式切换（实机/容器）、访问/错误日志
- **应用站点托管**：`update_app_sites` 维护 appupdate 应用域名站点（域名校验 + 文件服务），与用户站点互不干扰

## 部署方式

安装时可选 **实机** 或 **容器**：

- **实机**：系统已装 nginx 时复用其二进制、迁移配置到面板目录并停用系统服务；否则包管理器安装后部署到面板 runtime 目录（默认监听 127.0.0.1:8080）
- **容器**：`nginx:1.27-alpine` 镜像 + host 网络，配置/数据/runtime 目录按原路径挂载

## 面板页签

| 页签 | 说明 |
|---|---|
| 站点管理 | 站点增删改、下载路由开关、nginx.conf 编辑 |
| 实例控制 | 启动/停止/重启/重载、部署方式切换、日志 |

## CLI

```bash
aups plugins nginx status     # 状态与部署目录
aups plugins nginx install    # 部署到面板目录
aups plugins nginx remove     # 卸载（保留 config/data）
```

## 安装

```bash
aups plugins market install nginx                  # 实机（默认）
aups plugins market install nginx --deploy container   # 容器部署
```

## 说明

作为反代环境插件，可为 appupdate 等应用提供下载路由托管。下载路由需要在「站点管理」中新建**文件服务**站点（root 指向应用根目录）并勾选「下载路由」；渲染前实时向 appupdate 重取数据（CI 直传即时生效），latest 短链按文件日期指向最新文件。迁移：在 appupdate 应用页选择目标反代点「切换并迁移」（或 `aups plugins appupdate app switch nginx`），旧后端托管短链自动清空、站点保留，切回即恢复。
