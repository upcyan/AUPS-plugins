# lmd — LMD (maldet) 恶意软件扫描引擎

属性：依赖

LMD (maldet) 恶意软件扫描引擎（依赖插件）。插件负责安全安装、扫描和隔离编排，报告与隔离数据接口复用核心 `aups.core.hostsec`；通过标准能力 `provides.antivirus=lmd` 供核心发现。

## 迁移（旧安装 → 插件受管）

之前若已按旧方式装过 LMD (maldet) 二进制（`/usr/local/sbin/maldet`）：

- 安装插件时自动触发 `post_install()`：**强制统一通过插件重装**（先卸载旧二进制再重装）。
- 也可在面板任意时刻手动「重装（强制）」按钮，或：
  ```bash
  aups plugins market install lmd      # 触发 post_install 强制重装
  aups hostsec uninstall lmd           # 手动先卸载
  aups hostsec install lmd             # 再按需安装
  ```

## 说明

- 引擎按需扫描，无常驻进程；扫描结果进扫描报告，命中文件可隔离（`/usr/local/maldetect/quarantine`）并在面板恢复。
- 支持多扫描目录、扫描 ID 报告解析，以及按每个扫描 ID 执行隔离。
- 卸载插件（`remove()`）清理 LMD 二进制与隔离目录，保留报告数据目录（保数据卸载）。
- 核心安全引擎页仍可聚合展示 LMD 状态与隔离区。
