"""cyansecengine 扫描器：rkhunter / LMD(maldet) / YARA。

轻量主机加固工具封装：
- rkhunter：rootkit / 后门 / 基线偏离检测（按需运行，无常驻进程）
- LMD (maldet)：恶意文件 / Webshell 扫描，带隔离区（quarantine）
- YARA：自定义 / 订阅规则匹配（规则文件来自 subscribe 模块）

全部为按需扫描，不引入常驻进程，适配小内存 VPS。
"""

import datetime
import json
import os
import shutil
import time

from ... import config
from ... import pkg
from ...errors import AppError
from ...util import has_cmd, run

# 面板目录内各引擎工作目录
DATA_DIR = os.path.join(config.PANEL_DATA_DIR, "cyansecengine")
RULES_DIR = os.path.join(DATA_DIR, "rules")          # 订阅的 YARA 规则文件
REPORTS_DIR = os.path.join(DATA_DIR, "reports")      # 扫描报告（JSON）
YARA_RULES = os.path.join(DATA_DIR, "rules", "*.yar")
MALDET_BIN = "/usr/local/sbin/maldet"                # LMD 默认安装路径


def _ensure_dirs():
    os.makedirs(RULES_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)


def status():
    """各引擎安装状态与基本信息。"""
    _ensure_dirs()
    rk = shutil.which("rkhunter")
    yara = shutil.which("yara")
    maldet = os.path.isfile(MALDET_BIN) or shutil.which("maldet")
    rule_files = [f for f in os.listdir(RULES_DIR) if f.endswith((".yar", ".yara"))] if os.path.isdir(RULES_DIR) else []
    return {
        "rkhunter": {"installed": bool(rk), "binary": rk, "version": _version(rk, ["--version"])},
        "lmd": {"installed": bool(maldet), "binary": MALDET_BIN if os.path.isfile(MALDET_BIN) else shutil.which("maldet")},
        "yara": {"installed": bool(yara), "binary": yara, "version": _version(yara, ["--version"])},
        "rules": {"dir": RULES_DIR, "count": len(rule_files)},
        "reports_dir": REPORTS_DIR,
    }


def _version(bin_path, args):
    if not bin_path:
        return ""
    try:
        r = run([bin_path] + args, check=False)
        out = (r.stdout or r.stderr or "").strip()
        return out.splitlines()[0] if out else ""
    except Exception:
        return ""


# ---------- 安装 ----------

def install(tool):
    """安装指定引擎。tool: rkhunter / lmd / yara。"""
    tool = (tool or "").strip().lower()
    if tool == "rkhunter":
        pkg.install(["rkhunter"])
        return {"ok": True, "tool": "rkhunter", **status()["rkhunter"]}
    if tool == "yara":
        pkg.install(["yara"])
        return {"ok": True, "tool": "yara", **status()["yara"]}
    if tool == "lmd":
        return _install_lmd()
    raise AppError(f"未知引擎：{tool}（可选：rkhunter / lmd / yara）")


def _install_lmd():
    """安装 LMD (maldet)：官方 tarball 解压到 /usr/local（需 root）。

    官方地址 https://www.rfxn.com/downloads/maldetect-current.tar.gz。
    """
    if os.path.isfile(MALDET_BIN):
        return {"ok": True, "tool": "lmd", "installed": True}
    import tempfile
    import tarfile
    import urllib.request
    url = "https://www.rfxn.com/downloads/maldetect-current.tar.gz"
    tmp = tempfile.mkdtemp(prefix="aups-maldet-")
    try:
        tar_path = os.path.join(tmp, "maldet.tar.gz")
        req = urllib.request.Request(url, headers={"User-Agent": "aups-market/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(tar_path, "wb") as f:
                f.write(resp.read())
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(tmp)
        # 包内含 maldetect/ 目录与 install.sh
        src = None
        for entry in os.listdir(tmp):
            if entry == "maldetect" and os.path.isfile(os.path.join(tmp, entry, "install.sh")):
                src = os.path.join(tmp, entry)
                break
        if not src:
            raise AppError("maldet 安装包结构异常（未找到 install.sh）")
        r = run(["bash", os.path.join(src, "install.sh")], check=True)
        if not os.path.isfile(MALDET_BIN):
            raise AppError(f"maldet 安装未完成（{MALDET_BIN} 不存在）")
        return {"ok": True, "tool": "lmd", "installed": True, "detail": (r.stdout or "")[-300:]}
    except AppError:
        raise
    except Exception as e:
        raise AppError(f"maldet 下载/安装失败：{e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- 扫描 ----------

def scan(tool, paths=None, quarantine=True):
    """运行指定引擎扫描。paths 为要扫描的路径列表（默认面板数据目录 + 系统临时目录）。"""
    tool = (tool or "").strip().lower()
    st = status()
    if tool == "rkhunter":
        return _scan_rkhunter()
    if tool == "lmd":
        return _scan_lmd(paths, quarantine)
    if tool == "yara":
        return _scan_yara(paths)
    raise AppError(f"未知扫描引擎：{tool}（可选：rkhunter / lmd / yara）")


def _default_paths():
    return [config.PANEL_DATA_DIR, "/tmp", "/var/tmp"]


def _save_report(tool, result):
    _ensure_dirs()
    rid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    report = {
        "id": rid, "tool": tool, "time": time.time(),
        "ts": datetime.datetime.now().strftime("%F %T"),
        "result": result,
    }
    with open(os.path.join(REPORTS_DIR, f"{rid}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return rid


def reports():
    """列出历史扫描报告（id/时间/引擎/摘要）。"""
    if not os.path.isdir(REPORTS_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(REPORTS_DIR), reverse=True):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(REPORTS_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            out.append({
                "id": d.get("id", fn[:-5]),
                "ts": d.get("ts", ""),
                "tool": d.get("tool", ""),
                "summary": _report_summary(d.get("result", {})),
            })
        except (OSError, ValueError):
            continue
    return out


def report(rid):
    """读取单份报告。"""
    p = os.path.join(REPORTS_DIR, f"{rid}.json")
    if not os.path.isfile(p):
        raise AppError(f"报告不存在：{rid}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _report_summary(result):
    if not isinstance(result, dict):
        return str(result)[:120]
    if result.get("tool") == "rkhunter":
        return f"检测到可疑项 {result.get('suspected', 0)}，rootkit {result.get('rootkits', 0)}"
    if result.get("tool") == "lmd":
        return f"扫描 {result.get('files', 0)} 文件，发现 {result.get('hits', 0)}，隔离 {result.get('quarantined', 0)}"
    if result.get("tool") == "yara":
        return f"扫描 {result.get('files', 0)} 文件，命中 {result.get('hits', 0)}"
    return ""


# ---------- rkhunter ----------

def _scan_rkhunter():
    """运行 rkhunter --check，解析报告行。需 root。"""
    rk = shutil.which("rkhunter")
    if not rk:
        raise AppError("未安装 rkhunter，请先安装（安装后可执行 aups plugins cyansecengine install rkhunter）")
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
        "tool": "rkhunter",
        "returncode": r.returncode,
        "suspected": suspected, "rootkits": rootkits,
        "warnings": lines[:100],
        "raw": text[-4000:],
    }
    rid = _save_report("rkhunter", result)
    return {"report_id": rid, **result}


# ---------- LMD (maldet) ----------

def _scan_lmd(paths, quarantine):
    """运行 maldet --scan-all，收集命中文件并支持隔离。"""
    if not os.path.isfile(MALDET_BIN):
        raise AppError("未安装 LMD (maldet)，请先安装（install lmd）")
    targets = paths or _default_paths()
    for p in targets:
        if not os.path.exists(p):
            raise AppError(f"扫描路径不存在：{p}")
    args = [MALDET_BIN, "--scan-all", "--report", "--scan-ove", "--quarantine" if quarantine else "--no-quarantine"]
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
        "tool": "lmd",
        "returncode": r.returncode,
        "hits": hits, "quarantined": quarantined, "files": len(found),
        "found": found[:200],
        "raw": text[-4000:],
    }
    rid = _save_report("lmd", result)
    return {"report_id": rid, **result}


def quarantine_list():
    """列出 LMD 隔离区文件。"""
    qd = "/usr/local/maldetect/quarantine"
    if not os.path.isdir(qd):
        return []
    out = []
    for entry in sorted(os.listdir(qd), reverse=True):
        p = os.path.join(qd, entry)
        if os.path.isfile(p):
            out.append({"name": entry, "path": p, "size": os.path.getsize(p)})
    return out


def quarantine_restore(name):
    """恢复隔离文件到原路径。"""
    qd = "/usr/local/maldetect/quarantine"
    p = os.path.join(qd, name)
    if not os.path.isfile(p):
        raise AppError(f"隔离区无此文件：{name}")
    r = run([MALDET_BIN, "--restore", name], check=False)
    if r.returncode != 0:
        raise AppError(f"恢复失败：{(r.stderr or r.stdout or '').strip()}")
    return {"ok": True, "name": name}


# ---------- YARA ----------

def _scan_yara(paths):
    """用 rules 目录下所有 YARA 规则扫描路径，命中则列出文件与规则。"""
    yara = shutil.which("yara")
    if not yara:
        raise AppError("未安装 yara，请先安装（install yara）")
    rule_files = [f for f in os.listdir(RULES_DIR) if f.endswith((".yar", ".yara"))] if os.path.isdir(RULES_DIR) else []
    if not rule_files:
        raise AppError("没有可用 YARA 规则，请先订阅规则（规则订阅）或放入 rules/ 目录")
    targets = paths or _default_paths()
    hits = []
    for rf in rule_files:
        rule_path = os.path.join(RULES_DIR, rf)
        for target in targets:
            if os.path.isfile(target):
                r = run([yara, rule_path, target], check=False)
                if r.returncode == 0:
                    for ln in (r.stdout or "").splitlines():
                        hits.append({"rule": rf, "match": ln.split()[0], "file": " ".join(ln.split()[1:])})
            elif os.path.isdir(target):
                r = run([yara, "-r", rule_path, target], check=False)
                if r.returncode == 0:
                    for ln in (r.stdout or "").splitlines():
                        parts = ln.split()
                        hits.append({"rule": rf, "match": parts[0] if parts else "", "file": " ".join(parts[1:])})
    result = {
        "tool": "yara",
        "rule_count": len(rule_files),
        "hits": len(hits),
        "matches": hits[:200],
    }
    rid = _save_report("yara", result)
    return {"report_id": rid, **result}
