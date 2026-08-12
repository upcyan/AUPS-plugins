# AUPS 官方插件仓库

AUPS 综合性服务器面板的官方插件源。

## 结构

```
index.json                      # 市场清单（插件列表）
plugins/<name>/
    manifest.json               # 插件元数据（name/title/version/...）
    module/                     # Python 包 → 安装到 aups/modules/<name>/
    frontend.js                 # 前端脚本 → aups/web/static/plugins/<name>.js
```

## 安装 / 更新 / 卸载

Web 面板「插件中心 → 官方仓库」或 CLI：

```bash
aups plugins market list                     # 查看官方仓库插件
aups plugins market install appupdate        # 安装 / 更新
aups plugins market uninstall appupdate      # 卸载
```

## 新增插件

1. 在 `plugins/` 下建 `<name>/` 目录；
2. 放入 `manifest.json`、`module/`（含 `manifest.py`）、`frontend.js`；
3. 在 `index.json` 的 `plugins` 列表补一条记录。
