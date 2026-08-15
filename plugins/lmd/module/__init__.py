"""lmd 模块：LMD (maldet) 恶意软件扫描引擎（可选依赖插件）。

引擎状态/安装/卸载/扫描/报告/隔离区逻辑委托核心 aups.core.hostsec，
核心「安全引擎」页据此按需调用；本插件提供独立 API 与前端。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]