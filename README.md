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
| secgroup | 依赖 | nftables 原生安全组 |

各插件的详细说明见其自身目录下的 `README.md`（如 `plugins/appupdate/README.md`）。

## 结构

```
index.json                      # 市场清单（插件列表）
waf-rules.json                  # 公开 WAF 推荐规则订阅源
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

## 下载完整性（files 哈希，必须）

面板安装插件前会用 `index.json` 中该插件的 `files` 段（相对 `plugins/<name>/` 的
每文件 SHA-256）双向校验解压目录：声明文件哈希必须一致、且不允许出现未声明的
多余文件，失败会拒绝安装（防下载被篡改/注入）。**改动插件文件后必须重新生成
`files`**，否则面板无法安装该插件。可用以下脚本生成：

```bash
python gen_index_hashes.py   # 遍历 plugins/ 各插件并写入 index.json 的 files
```

- 生成脚本不入库（临时使用），但改动插件后提交前务必重跑。
- 新增/删除/重命名插件目录里的文件都要同步刷新 `files`。
