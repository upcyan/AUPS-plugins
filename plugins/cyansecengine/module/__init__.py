"""cyansecengine 模块：轻量主机安全加固（可选）。

包含：扫描器（scanner：rkhunter / LMD / YARA）、在线规则订阅（subscribe）。
与核心 WAF 模板（aups.core.waf）互补：WAF 管流量层，本插件管主机层
（rootkit / 恶意文件 / Webshell）。
"""

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
