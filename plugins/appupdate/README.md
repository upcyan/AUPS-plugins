# appupdate — 应用更新管理

属性：功能

APK 更新：应用注册/版本、存储与配额、下载统计、CI 上传用户与 SSH 公钥。

依赖：需要代理能力（`depends: [{capability: proxy}]`，与 caddy 等反代环境插件搭配使用）。

## 功能

- **应用管理**：应用注册/版本、存储与配额、APK 管理、未注册检查
- **CI 用户**：APK 上传账号与目录 ACL 授权
- **SSH 公钥**：CI 用户的上传鉴权公钥管理
- **存储**：存储用量、配额、强制执行
- **下载统计**：下载量统计（总览卡片）

## 面板页签

| 页签 | 说明 |
|---|---|
| 应用管理 | 应用注册/版本、存储与配额、APK 管理、未注册检查 |
| CI 用户 | APK 上传账号与目录 ACL 授权 |
| SSH 公钥 | CI 用户的上传鉴权公钥管理 |

## CLI

```bash
aups app ...       # 应用管理
aups storage ...   # 存储管理
aups user ...      # CI 用户管理
aups ssh ...       # SSH 公钥管理
```

## 安装

```bash
aups plugins market install appupdate
```

## 说明

需要面板已具备反代能力（安装 caddy 或 nginx 环境插件）才能完整使用下载路由等能力。
