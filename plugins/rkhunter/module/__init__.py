"""rkhunter 模块：主机入侵检测引擎（可选依赖插件）。

引擎状态/安装/卸载/扫描/报告逻辑委托核心 aups.core.hostsec，
核心「安全引擎」页据此按需调用；本插件提供独立 API 与前端。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]