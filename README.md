# AUPS 插件仓库

AUPS 综合性服务器面板的插件源。

## 插件

| 插件 | 属性 | 说明 |
|---|---|---|
| appupdate | 功能 | APK 更新：应用注册/版本、存储与配额、下载统计、CI 用户与 SSH 公钥 |
| caddy | 环境 | Caddy 反代：托管片段（下载路由/WAF）、WAF 防护、access 日志、Caddy 端口与防火墙 |

## 结构

```
index.json                      # 市场清单（插件列表）
plugins/<name>/
    manifest.json               # 插件元数据（name/title/attr/version/...）
    module/                     # Python 包 → 安装到 aups/modules/<name>/
    frontend.js                 # 前端脚本 → aups/web/static/plugins/<name>.js
```

## 安装 / 更新 / 卸载

Web 面板「插件中心 → 插件仓库」或 CLI：

```bash
aups plugins market list                     # 查看插件仓库
aups plugins market install appupdate        # 安装 / 更新
aups plugins market uninstall appupdate      # 卸载
```

## 新增插件

1. 在 `plugins/` 下建 `<name>/` 目录；
2. 放入 `manifest.json`、`module/`（含 `manifest.py`）、`frontend.js`；
3. 在 `index.json` 的 `plugins` 列表补一条记录。
