"""lmd 引擎委托模块。

全部逻辑委托核心 aups.core.hostsec（安装/卸载/扫描/报告/隔离区与数据目录
均为核心持有），保证迁移上下文（强制重装）与插件粒度解耦。
"""

from ...core import hostsec

TOOL = "lmd"


def status():
    return hostsec.status().get("lmd", {})


def install():
    """核心按需安装 LMD（无旧二进制时）。"""
    return hostsec.install("lmd")


def reinstall():
    """强制重装为插件受管：先卸载旧二进制再重装。"""
    return hostsec.reinstall("lmd")


def uninstall():
    """卸载 LMD 二进制（插件卸载钩子用）。"""
    return hostsec.uninstall("lmd")


def scan(paths=None, quarantine=True):
    return hostsec.scan("lmd", paths, quarantine)


def reports():
    return hostsec.reports()


def report(rid):
    return hostsec.report(rid)


def quarantine_list():
    return hostsec.quarantine_list()


def quarantine_restore(name):
    return hostsec.quarantine_restore(name)


def post_install():
    """market 安装/更新后执行：强制统一通过插件重装（卸载旧二进制再装）。"""
    return reinstall()


def remove():
    """插件卸载钩子：清理部署的软件（二进制），保留数据目录（保数据卸载）。"""
    try:
        return uninstall()
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["TOOL", "status", "install", "reinstall", "uninstall",
           "scan", "reports", "report", "quarantine_list", "quarantine_restore",
           "post_install", "remove"]