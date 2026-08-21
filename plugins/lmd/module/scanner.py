"""LMD (maldet) 引擎（插件负责二进制部署与扫描解析）。

架构分层：
- 本插件实现：二进制下载/解压/安装/卸载（reinstall 强制重装）、扫描执行与结果解析；
- 共享数据层（报告/隔离区读写）委托核心 aups.core.hostsec。
"""

import os
import re
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
    binary = MALDET_BIN if os.path.isfile(MALDET_BIN) else (shutil.which("maldet") or "")
    return {"installed": bool(binary), "binary": binary,
            "version": hostsec.bin_version(binary, ["-v"]),
            "default_paths": _default_paths(), "report_count": len(reports())}


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
            _safe_extract(tf, tmp)
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
    """逐目录运行 maldet 扫描，再按扫描 ID 获取报告并按需隔离。"""
    if not os.path.isfile(MALDET_BIN):
        raise AppError("未安装 LMD (maldet)，请先安装（install lmd）")
    targets = ([paths] if isinstance(paths, str) else list(paths or _default_paths()))
    for p in targets:
        if not os.path.exists(p):
            raise AppError(f"扫描路径不存在：{p}")
    scan_ids, found, raw_parts, errors = [], [], [], []
    hits = quarantined = files = 0
    returncode = 0
    for target in targets:
        scanned = run([MALDET_BIN, "--scan-all", target], check=False)
        returncode = max(returncode, int(scanned.returncode or 0))
        output = ((scanned.stdout or "") + "\n" + (scanned.stderr or "")).strip()
        raw_parts.append(f"===== {target} =====\n{output}")
        scan_id = _scan_id(output)
        if not scan_id:
            errors.append(f"{target}: 未取得扫描 ID（exit {scanned.returncode}）")
            continue
        scan_ids.append(scan_id)
        reported = run([MALDET_BIN, "--report", scan_id], check=False)
        report_text = ((reported.stdout or "") + "\n" + (reported.stderr or "")).strip()
        raw_parts.append(f"===== report {scan_id} =====\n{report_text}")
        hits += _report_number(report_text, "TOTAL HITS")
        files += _report_number(report_text, "TOTAL FILES")
        found.extend(ln.strip() for ln in report_text.splitlines()
                     if "FOUND" in ln.upper() or "MALWARE" in ln.upper() and "HIT" in ln.upper())
        if quarantine and _report_number(report_text, "TOTAL HITS") > 0:
            quarantined_run = run([MALDET_BIN, "--quarantine", scan_id], check=False)
            qtext = ((quarantined_run.stdout or "") + "\n" +
                     (quarantined_run.stderr or "")).strip()
            raw_parts.append(f"===== quarantine {scan_id} =====\n{qtext}")
            if quarantined_run.returncode == 0:
                quarantined += _report_number(report_text, "TOTAL HITS")
            else:
                errors.append(f"{target}: 隔离失败（exit {quarantined_run.returncode}）")
    if not scan_ids:
        raise AppError("LMD 扫描失败：" + ("；".join(errors) or "未生成扫描报告"))
    text = "\n".join(raw_parts)
    result = {
        "tool": TOOL,
        "returncode": returncode, "targets": list(targets), "scan_ids": scan_ids,
        "hits": hits, "quarantined": quarantined, "files": files,
        "found": found[:200],
        "errors": errors,
        "raw": text[-4000:],
    }
    rid = hostsec.save_report(TOOL, result)
    return {"report_id": rid, **result}


def _default_paths():
    return [config.PANEL_DATA_DIR, "/tmp", "/var/tmp"]


def _safe_extract(tf, dest):
    """拒绝绝对路径、目录穿越和链接成员，避免安装包写出临时目录。"""
    base = os.path.realpath(dest)
    for member in tf.getmembers():
        target = os.path.realpath(os.path.join(base, member.name))
        if (not (target == base or target.startswith(base + os.sep))
                or member.issym() or member.islnk()):
            raise AppError(f"maldet 安装包包含非法路径：{member.name}")
    tf.extractall(dest)


def _scan_id(text):
    for pattern in (r"SCAN\s+ID\s*[:=]\s*\{?([\w.-]+)",
                    r"--report\s+([\w.-]+)"):
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return match.group(1).rstrip("}")
    return ""


def _report_number(text, label):
    match = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", text or "", re.IGNORECASE)
    return int(match.group(1)) if match else 0


def reports():
    """读取共享数据层的扫描报告列表。"""
    return [item for item in hostsec.reports() if item.get("tool") == TOOL]


def report(rid):
    """读取共享数据层的单份报告。"""
    data = hostsec.report(rid)
    if data.get("tool") != TOOL:
        raise AppError("报告不属于 LMD")
    return data


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
