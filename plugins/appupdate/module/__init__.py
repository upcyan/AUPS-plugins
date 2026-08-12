"""appupdate 模块：APK 应用更新管理（可选）。

包含：应用注册/版本（apps）、APK 存储与配额（storage）、WAF（waf）、
反代下载路由（rproxy）、下载统计（downloads）。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
