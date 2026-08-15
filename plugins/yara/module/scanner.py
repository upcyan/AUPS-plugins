"""yara 引擎扫描委托模块。

全部逻辑委托核心 aups.core.yara：状态 / 安装 / 扫描 / 报告 / 订阅。
规则数据唯一来源为核心 data/yara/ 目录（由核心持有）。
"""

from ...core import yara

status = yara.status
install = yara.install
scan = yara.scan
scan_file = yara.scan_file
reports = yara.reports
report = yara.report
list_subs = yara.list_subs
add_sub = yara.add_sub
remove_sub = yara.remove_sub
sync = yara.sync

__all__ = ["status", "install", "scan", "scan_file", "reports", "report",
           "list_subs", "add_sub", "remove_sub", "sync"]