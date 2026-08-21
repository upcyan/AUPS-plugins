# rkhunter — 主机入侵检测引擎

属性：依赖

rkhunter 主机入侵检测引擎（依赖插件）。插件负责安装、扫描和警告解析，报告接口复用核心 `aups.core.hostsec`；通过标准能力 `provides.ids=rkhunter` 供核心发现。

## 迁移（旧安装 → 插件受管）

之前若已按旧方式装过 rkhunter 二进制：

- 安装插件时自动触发 `post_install()`：**强制统一通过插件重装**（先卸载旧二进制再重装）。
- 也可在面板任意时刻手动「重装（强制）」按钮，或：
  ```bash
  aups plugins market install rkhunter   # 触发 post_install 强制重装
  aups hostsec uninstall rkhunter        # 手动先卸载
  aups hostsec install rkhunter          # 再按需安装
  ```

## 说明

- 引擎按需扫描，无常驻进程。
- 卸载插件（`remove()`）只清理 rkhunter 二进制，保留报告数据目录（保数据卸载）。
- 核心安全引擎页仍可聚合展示 rkhunter 状态。
