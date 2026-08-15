"""cyansecengine（青·擎）模块：占位壳。

v3.0.0 起不再提供逻辑模块 —— 主机安全 / 实时防护 / YARA 引擎的
实现已并入核心（aups.core.hostsec / aups.core.rtguard / aups.core.yara）。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]