# nginx — Nginx 环境

属性：环境

Nginx 反代：站点配置、证书（通过 certbot/acme 申请）。

## 功能

- **Nginx 反代**：Nginx 状态、安装与卸载（部署到面板目录）

## 面板页签

| 页签 | 说明 |
|---|---|
| Nginx 反代 | Nginx 状态、安装与卸载 |

## CLI

```bash
aups nginx ...   # Nginx 反代管理
```

## 安装

```bash
aups plugins market install nginx
```

## 说明

Nginx 环境插件，可提供反代能力。证书可通过 certbot / acme 依赖插件申请。
