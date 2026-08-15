"""LMD (maldet) 引擎（插件负责二进制部署与扫描解析）。

架构分层：
- 本插件实现：二进制下载/解压/安装/卸载（reinstall 强制重装）、扫描执行与结果解析；
- 共享数据层（报告/隔离区读写）委托核心 aups.core.hostsec。
"""

import os
import shutil
import subprocess
import tempfile
import tarfile
import urllib.request

from ... import config
from ...core import hostsec
from ...core.util import run
from ...errors import AppError

TOOL = "lmd"
MALDET_BIN = hostsec.MALDET_BIN  # /usr/local/sbin/maldet
MALDET_DIR = "/usr/local/maldetect"


def status():
    """LMD 二进制状态。"""
    maldet = os.path.isfile(MALDET_BIN) or shutil.which("maldet")
    return {"installed": bool(maldet),
            "binary": MALDET_BIN if os.path.isfile(MALDET_BIN) else (shutil.which("maldet") or "")}


def install():
    """部署 LMD：官方 tarball 下载解压安装（需 root）。"""
    return _install_lmd()


def reinstall():
    """强制重装为插件受管：先卸载旧二进制再重装。"""
    st = status()
    if st["installed"]:
        uninstall()
    return install()


def uninstall():
    """卸载 LMD (maldet)：删除其安装目录与二进制（保留面板数据目录中的报告）。"""
    removed = []
    if os.path.isfile(MALDET_BIN):
        for p in (MALDET_BIN, "/usr/local/bin/maldet"):
            if os.path.exists(p):
                os.remove(p)
                removed.append(p)
    if os.path.isdir(MALDET_DIR):
        # 通过脚本卸载释放系统级 cron 等配置，随后还需删残留目录
        r = run(["bash", os.path.join(MALDET_DIR, "uninstall.sh")], check=False)
        if os.path.isdir(MALDET_DIR):
            shutil.rmtree(MALDET_DIR, ignore_errors=True)
            removed.append(MALDET_DIR)
    return {"ok": True, "tool": TOOL, "uninstalled": bool(removed),
            "removed": removed, **status()}


def _install_lmd():
    """安装 LMD (maldet)：官方 tarball 解压到 /usr/local（需 root）。"""
    if os.path.isfile(MALDET_BIN):
        return {"ok": True, "tool": TOOL, "installed": True}
    url = "https://www.rfxn.com/downloads/maldetect-current.tar.gz"
    tmp = tempfile.mkdtemp(prefix="aups-maldet-")
    try:
        tar_path = os.path.join(tmp, "maldet.tar.gz")
        req = urllib.request.Request(url, headers={"User-Agent": "aups-hostsec/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(tar_path, "wb") as f:
                f.write(resp.read())
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(tmp)
        # 包内含 maldetect-<版本>/ 目录与 install.sh（版本号随包变化，做前缀匹配）
        src = None
        for entry in os.listdir(tmp):
            if entry.startswith("maldetect") and os.path.isfile(os.path.join(tmp, entry, "install.sh")):
                src = os.path.join(tmp, entry)
                break
        if not src:
            raise AppError("maldet 安装包结构异常（未找到 install.sh）")
        # install.sh 依赖相对 files/ 路径，需在其所在目录内执行
        r = run(["bash", "install.sh"], check=True, cwd=src)
        if not os.path.isfile(MALDET_BIN):
            raise AppError(f"maldet 安装未完成（{MALDET_BIN} 不存在）")
        return {"ok": True, "tool": TOOL, "installed": True, "detail": (r.stdout or "")[-300:]}
    except AppError:
        raise
    except Exception as e:
        raise AppError(f"maldet 下载/安装失败：{e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def scan(paths=None, quarantine=True):
    """运行 maldet --scan-all，收集命中文件并支持隔离。"""
    if not os.path.isfile(MALDET_BIN):
        raise AppError("未安装 LMD (maldet)，请先安装（install lmd）")
    targets = paths or _default_paths()
    for p in targets:
        if not os.path.exists(p):
            raise AppError(f"扫描路径不存在：{p}")
    args = [MALDET_BIN, "--scan-all", "--report", "--scan-ove",
            "--quarantine" if quarantine else "--no-quarantine"]
    args += list(targets)
    r = run(args, check=False)
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    hits = text.count("FOUND")
    quarantined = text.count("quarantined") + text.count("Quarantined")
    # 命中文件行形如：{/path} -> FOUND {/quarantine/location}
    found = []
    for ln in text.splitlines():
        if "FOUND" in ln:
            found.append(ln.strip())
    result = {
        "tool": TOOL,
        "returncode": r.returncode,
        "hits": hits, "quarantined": quarantined, "files": len(found),
        "found": found[:200],
        "raw": text[-4000:],
    }
    rid = hostsec.save_report(TOOL, result)
    return {"report_id": rid, **result}


def _default_paths():
    return [config.PANEL_DATA_DIR, "/tmp", "/var/tmp"]


def reports():
    """读取共享数据层的扫描报告列表。"""
    return hostsec.reports()


def report(rid):
    """读取共享数据层的单份报告。"""
    return hostsec.report(rid)


def quarantine_list():
    """读取共享数据层的隔离区列表。"""
    return hostsec.quarantine_list()


def quarantine_restore(name):
    """恢复隔离文件到原路径。"""
    return hostsec.quarantine_restore(name)


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
           "scan", "reports", "report", "quarantine_list", "quarantine_restore",
           "post_install", "remove"]