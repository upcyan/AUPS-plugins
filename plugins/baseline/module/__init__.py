"""baseline 模块：VPS 基线检查（纯只读审计功能插件）。

检查项实现在 scanner.py（账号/系统配置/内核网络/服务应用四类），
报告数据层委托核心 aups.core.hostsec。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]