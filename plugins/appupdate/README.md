# appupdate — 应用更新管理

属性：功能

APK 更新：应用注册/版本、存储与配额、下载统计、CI 上传用户与 SSH 公钥。

依赖：需要代理能力（`depends: [{capability: proxy}]`，与 caddy 等反代环境插件搭配使用）。

## 功能

- **应用管理**：应用注册/版本、存储与配额、APK 管理、未注册检查
- **版本更新日志**：存储与版本页按版本查看/编辑更新日志。日志合并自两处：
  应用目录下 CI 维护的 `update.json`（`changelogs[].versionName/note`，App 端
  展示的同一来源，面板编辑直接写回，CI merge 默认不覆盖已有 note）+ 面板
  补写层（无 update.json 的应用）；清空保存即删除补写层记录
- **update.json 滚动窗口**：`changelogs` 超过 30 条时自动裁剪到最近 30 条，
  溢出条目按时间正序归档到应用目录 `update-archive/changelogs-<分片>.json`
  （每片 100 条，App 不读）；CI 的 merge 脚本与工作流零改动，窗口由面板
  周期同步在服务端收敛
- **下载路由自动同步**：新建/删除应用、保存部署配置时自动把版本短链与 latest
  重定向同步到反代（latest 按文件日期指向最新文件，CI 经 SSH 直传的新文件
  由渲染前实时刷新与周期任务跟进），无需再到 VPS 手工编辑 Caddyfile
- **反代切换迁移**：caddy/nginx 之间一键切换默认反代（应用页「切换并迁移」或
  `aups plugins appupdate app switch <后端>`）——旧后端托管短链自动清空、
  应用站点保留，新后端按最新数据重建站点与路由，切回即恢复
- **CI 推送通知**：CI 流水线推送 APK 后回调 `POST /api/apps/ci/notify`（令牌鉴权，
  面板应用页查看/复制 curl/重置），立即刷新下载路由，免等周期任务
- **新项目引导注册**：CI 直传的新目录不自动注册——应用页顶部提示未注册目录
  （可勾选部分或全选批量注册）；可选启用 systemd path unit 监听 BASE_DIR
  （`aups plugins appupdate watch on`），新目录出现即记录事件并刷新路由
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
aups plugins appupdate app caddy            # 手动同步下载路由（默认自动触发）
aups plugins appupdate cron routes          # 安装每10分钟路由同步定时任务（CI 直传场景）
aups plugins appupdate app backends         # 列出反代后端及能力
aups plugins appupdate app switch nginx     # 切换反代并迁移下载路由/应用站点
aups plugins appupdate ci token             # 查看 CI 通知令牌（--reset 重置）
aups plugins appupdate watch on             # BASE_DIR 新目录监听（on/off/status）
```

## 安装

```bash
aups plugins market install appupdate
```

## 说明

需要面板已具备反代能力（安装 caddy 或 nginx 环境插件）才能完整使用下载路由等能力。
