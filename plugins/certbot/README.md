# certbot — Certbot 证书签发

属性：依赖

Let's Encrypt 证书签发（certbot）：申请/续期，证书落在面板数据目录。

## 功能

- **证书签发**：Certbot 状态、安装/申请证书

## 面板页签

| 页签 | 说明 |
|---|---|
| 证书签发 | Certbot 状态、安装/申请证书 |

## CLI

```bash
aups certbot ...   # Certbot 证书管理
```

## 安装

```bash
aups plugins market install certbot
```

## 说明

依赖插件，为 nginx 等环境插件提供证书申请能力。证书将保存于面板数据目录。
