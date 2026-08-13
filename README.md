# AUPS 插件仓库

AUPS 综合性服务器面板的官方插件源。

## 插件

| 插件 | 属性 | 说明 |
|---|---|---|
| appupdate | 功能 | 应用更新管理 |
| caddy | 环境 | Caddy 反代与 WAF |
| nginx | 环境 | Nginx 反代 |
| certbot | 依赖 | Let's Encrypt 证书签发（certbot） |
| acme | 依赖 | acme.sh 证书签发 |

各插件的详细说明见其自身目录下的 `README.md`（如 `plugins/appupdate/README.md`）。

## 结构

```
index.json                      # 市场清单（插件列表）
plugins/<name>/
    manifest.json               # 插件元数据（name/title/attr/version/...）
    module/                     # Python 包 → 安装到 aups/modules/<name>/
    frontend.js                 # 前端脚本 → aups/web/static/plugins/<name>.js
    README.md                   # 插件自身说明
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
3. 在 `index.json` 的 `plugins` 列表补一条记录；
4. 可为本插件编写 `README.md` 说明用途与使用方式。
