"""yara 模块：YARA 规则引擎（可选依赖插件）。

规则数据（rules/ 目录与订阅清单）由核心持有（aups.core.yara），
本插件提供引擎安装 / 扫描 / 订阅的 HTTP API 与前端，全部逻辑委托核心，
供核心主机安全（hostsec）与 cyansecengine（青·擎）调用。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
