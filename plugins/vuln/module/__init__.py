"""漏洞检测模块：系统与部署软件漏洞检测（功能插件）。

检测/修复实现在 scanner.py（系统安全更新、部署软件版本比对），
报告数据层委托核心 aups.core.hostsec。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]