"""rkhunter 引擎（插件负责二进制部署与扫描解析）。

架构分层：
- 本插件实现：二进制部署（install/reinstall/uninstall）、扫描执行与结果解析；
- 共享数据层（报告读写）委托核心 aups.core.hostsec（save_report/reports/report）。
"""

import shutil

from ...core import hostsec
from ...core import pkg
from ...core.util import run
from ...errors import AppError

TOOL = "rkhunter"


def status():
    """rkhunter 二进制状态（版本探测由核心 bin_version 辅助）。"""
    rk = shutil.which("rkhunter")
    return {"installed": bool(rk), "binary": rk or "",
            "version": hostsec.bin_version(rk, ["--version"])}


def install():
    """部署 rkhunter：系统包管理器安装。"""
    pkg.install(["rkhunter"])
    return {"ok": True, "tool": TOOL, **status()}


def reinstall():
    """强制重装为插件受管：先卸载旧二进制再重装。"""
    st = status()
    if st["installed"]:
        uninstall()
    return install()


def uninstall():
    """卸载 rkhunter 二进制（插件卸载钩子用）。"""
    try:
        pkg.uninstall(["rkhunter"])
    except AppError as e:
        raise AppError(f"rkhunter 卸载失败：{e}")
    return {"ok": True, "tool": TOOL, "uninstalled": True, **status()}


def scan(paths=None, quarantine=True):
    """运行 rkhunter --check，解析警告行。需 root。"""
    rk = shutil.which("rkhunter")
    if not rk:
        raise AppError("未安装 rkhunter，请先安装（安装后可执行 aups hostsec install rkhunter）")
    # --sk 跳过明文密码提示，--rwo 仅报告警告；报告文本输出到 stdout
    r = run([rk, "--check", "--sk", "--rwo", "--nocolors"], check=False)
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    suspected = rootkits = 0
    lines = []
    for ln in text.splitlines():
        if "Rootkit Hunter" in ln or not ln.strip():
            continue
        if ln.strip().startswith("Warning:"):
            lines.append(ln.strip())
            if "rootkit" in ln.lower():
                rootkits += 1
            else:
                suspected += 1
    result = {
        "tool": TOOL,
        "returncode": r.returncode,
        "suspected": suspected, "rootkits": rootkits,
        "warnings": lines[:100],
        "raw": text[-4000:],
    }
    rid = hostsec.save_report(TOOL, result)
    return {"report_id": rid, **result}


def reports():
    """读取共享数据层的扫描报告列表。"""
    return hostsec.reports()


def report(rid):
    """读取共享数据层的单份报告。"""
    return hostsec.report(rid)


def post_install():
    """market 安装/更新后执行：强制统一通过本插件重装（卸载旧二进制再装）。"""
    return reinstall()


def remove():
    """插件卸载钩子：清理部署的软件（二进制），保留数据目录（保数据卸载）。"""
    try:
        return uninstall()
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["TOOL", "status", "install", "reinstall", "uninstall",
           "scan", "reports", "report", "post_install", "remove"]