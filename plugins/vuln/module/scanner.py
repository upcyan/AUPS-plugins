"""漏洞检测（插件负责检测与修复，报告数据层委托核心 hostsec）。

覆盖两大类：
- 系统漏洞：按发行版查询待安全更新/待更新包数量、是否需重启、自动安全更新是否启用；
- 部署的软件漏洞：面板部署/系统关键软件（nginx/caddy/certbot/acme.sh/rkhunter/maldet/
  yara/fail2ban/openssl/curl/redis/nginx）的已装版本与源仓库候选版本比对，
  落后即提示升级方案。

每项返回 {id, group, title, ok, current, expected, advice, critical, fixable, pkg}：
- ok=False 且 fixable=True：前端显示「一键修复」；
- 修复入口：fix(scope) 按包管理器执行安全更新/补丁安装（apt --only-upgrade / dnf
  --security / apk upgrade / zypper patch 等）。
"""

import os
import re
import subprocess

from ...core import hostsec
from ...core import pkg as CORE_PKG
from ...core.util import has_cmd
from ...errors import AppError

TOOL = "vuln"

# 部署/关键软件清单：binary 探测名 -> (显示名, 版本探测命令, 包管理器回退包名)
_SOFTWARE = [
    ("nginx", "Nginx", ["nginx", "-v"], "nginx"),
    ("caddy", "Caddy", ["caddy", "version"], "caddy"),
    ("certbot", "Certbot", ["certbot", "--version"], "certbot"),
    ("acme.sh", "acme.sh", ["acme.sh", "--version"], None),
    ("rkhunter", "rkhunter", ["rkhunter", "--version"], "rkhunter"),
    ("maldet", "LMD (maldet)", ["maldet", "-v"], None),
    ("yara", "YARA", ["yara", "--version"], "yara"),
    ("fail2ban-client", "fail2ban", ["fail2ban-client", "--version"], "fail2ban"),
    ("openssl", "OpenSSL", ["openssl", "version"], "openssl"),
    ("curl", "curl", ["curl", "--version"], "curl"),
    ("redis-server", "Redis", ["redis-server", "--version"], "redis-server"),
]


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _qrun(args, timeout=30):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception:
        return None


def _is_linux():
    return os.name == "posix" and os.path.isdir("/proc/sys")


def _bin_version(bin_path, args):
    r = _qrun(args, timeout=10)
    if not r:
        return ""
    out = (r[1] or r[2] or "").strip()
    return out.splitlines()[0] if out else ""


def _pkg_candidate(pkg):
    """返回包在源仓库的候选版本（未安装返回 None）。跨包管理器适配。"""
    pm = CORE_PKG.detect()
    if not pm or not pkg:
        return None
    try:
        if pm == "apt":
            r = _qrun(["apt-cache", "policy", pkg], timeout=20)
            if not r:
                return None
            for ln in (r[1] or "").splitlines():
                m = re.search(r"Candidate:\s*(\S+)", ln)
                if m:
                    return m.group(1)
        elif pm in ("dnf", "yum"):
            r = _qrun([pm, "-q", "list", "available", pkg], timeout=20)
            if not r:
                return None
            for ln in (r[1] or "").splitlines():
                if "." in ln:
                    parts = ln.split()
                    if len(parts) >= 2:
                        return parts[1]
        elif pm == "apk":
            r = _qrun(["apk", "search", "-x", "-s", pkg], timeout=20)
            if not r:
                return None
            for ln in (r[1] or "").splitlines():
                if ln.strip():
                    parts = ln.split()
                    if len(parts) >= 2:
                        return parts[1]
    except Exception:
        return None
    return None


# ---------- 系统漏洞 ----------

def _sys_security_updates():
    """待安全更新数量（按发行版专用通道查询；无安全通道的以全部待更新替代）。"""
    if not _is_linux():
        return None
    pm = CORE_PKG.detect()
    if not pm:
        return None
    count = None
    detail = ""
    if pm == "apt":
        r = _qrun(["sh", "-c",
                    "apt-get -s upgrade 2>/dev/null | grep -cE 'Inst .*\\((.*security.*)\\)'"],
                   timeout=40)
        if r:
            count = int(r[1].strip() or "0")
            detail = "apt-get -s upgrade 安全通道"
    elif pm == "dnf":
        r = _qrun(["dnf", "-q", "check-update", "--security"], timeout=60)
        if r:
            count = len([ln for ln in (r[1] or "").splitlines() if "." in ln]) if r[1] else 0
            detail = "dnf check-update --security"
    elif pm == "yum":
        r = _qrun(["yum", "-q", "check-update", "--security"], timeout=60)
        if r:
            count = len([ln for ln in (r[1] or "").splitlines() if "." in ln]) if r[1] else 0
            detail = "yum check-update --security"
    elif pm == "apk":
        r = _qrun(["sh", "-c", "apk list -u 2>/dev/null | wc -l"], timeout=30)
        if r:
            count = int(r[1].strip() or "0")
            detail = "apk list -u（Alpine 无安全通道，按待更新计）"
    elif pm == "zypper":
        r = _qrun(["zypper", "--non-interactive", "list-updates", "--type", "security"], timeout=60)
        if r:
            count = len([ln for ln in (r[1] or "").splitlines()
                         if re.match(r"^[ivIU]", ln.strip())])
            detail = "zypper list-updates --type security"
    elif pm == "pacman":
        r = _qrun(["sh", "-c", "checkupdates 2>/dev/null | wc -l"], timeout=40)
        if r:
            count = int(r[1].strip() or "0")
            detail = "checkupdates（Arch 无安全通道，按待更新计）"
    return {
        "id": "sys_security_updates", "group": "系统漏洞",
        "title": "待安全更新/补丁", "critical": count is not None and count > 0,
        "ok": count == 0 if count is not None else None,
        "current": f"{count} 个" if count is not None else "不可查询",
        "expected": "无待安装的安全更新（CVE 补丁应尽快安装）",
        "advice": "执行安全更新：面板「漏洞检测 → 一键修复」；命令行："
                  + {"apt": "apt-get install --only-upgrade -y $(apt-get -s upgrade | grep -E 'Inst .*\\(.*security.*\\)' | awk '{print $2}')",
                     "dnf": "dnf upgrade --security -y", "yum": "yum update --security -y",
                     "apk": "apk upgrade", "zypper": "zypper patch",
                     "pacman": "pacman -Syu --noconfirm"}.get(pm, "对应包管理器安全更新"),
        "fixable": count is not None and count > 0,
        "fix_scope": "security",
        "pkg": None,
    }


def _sys_all_updates():
    """全部待更新包数量（与安全通道区分，衡量整体补丁水平）。"""
    if not _is_linux():
        return None
    pm = CORE_PKG.detect()
    if not pm:
        return None
    count = None
    if pm == "apt":
        r = _qrun(["sh", "-c", "apt list --upgradable 2>/dev/null | tail -n +2 | wc -l"], timeout=40)
        if r:
            count = int(r[1].strip() or "0")
    elif pm in ("dnf", "yum"):
        r = _qrun([pm, "-q", "check-update"], timeout=60)
        if r:
            count = len([ln for ln in (r[1] or "").splitlines() if "." in ln]) if r[1] else 0
    elif pm == "apk":
        r = _qrun(["sh", "-c", "apk list -u 2>/dev/null | wc -l"], timeout=30)
        if r:
            count = int(r[1].strip() or "0")
    elif pm == "zypper":
        r = _qrun(["zypper", "--non-interactive", "list-updates"], timeout=60)
        if r:
            count = len([ln for ln in (r[1] or "").splitlines()
                         if re.match(r"^[ivIU]", ln.strip())])
    elif pm == "pacman":
        r = _qrun(["sh", "-c", "checkupdates 2>/dev/null | wc -l"], timeout=40)
        if r:
            count = int(r[1].strip() or "0")
    return {
        "id": "sys_all_updates", "group": "系统漏洞",
        "title": "全部待更新包", "critical": False,
        "ok": count == 0 if count is not None else None,
        "current": f"{count} 个" if count is not None else "不可查询",
        "expected": "定期整体升级保持软件处于最新安全状态",
        "advice": "执行整体升级：apt upgrade / dnf upgrade / apk upgrade 等（或使用本页「全部修复」）",
        "fixable": count is not None and count > 0,
        "fix_scope": "all",
        "pkg": None,
    }


def _sys_reboot():
    """是否需要重启（内核/关键库更新后常见）。"""
    if not _is_linux():
        return None
    need = os.path.isfile("/var/run/reboot-required")
    return {
        "id": "sys_reboot", "group": "系统漏洞",
        "title": "需要重启系统", "critical": False,
        "ok": not need,
        "current": "是（/var/run/reboot-required）" if need else "否",
        "expected": "安装内核/glibc 等关键更新后应重启以加载新版本",
        "advice": "合适时机执行 reboot（会中断服务），确认更新确已生效",
        "fixable": False,
        "pkg": None,
    }


def _sys_unattended():
    """自动安全更新：apt 20auto-upgrades / dnf-automatic。"""
    if not _is_linux():
        return None
    on = False
    detail = ""
    text = _read("/etc/apt/apt.conf.d/20auto-upgrades")
    if text is not None and re.search(
            r'APT::Periodic::Unattended-Upgrade\s+"1"', text):
        on = True
        detail = "unattended-upgrades"
    if has_cmd("dnf-automatic"):
        r = _qrun(["systemctl", "is-active", "dnf-automatic.timer"], timeout=10)
        if r and r[1].strip() == "active":
            on = True
            detail = "dnf-automatic"
    return {
        "id": "sys_unattended", "group": "系统漏洞",
        "title": "自动安全更新", "critical": False,
        "ok": on,
        "current": f"已启用（{detail}）" if on else "未启用",
        "expected": "启用自动安全更新（unattended-upgrades / dnf-automatic）",
        "advice": "apt: apt install unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades；"
                  "dnf: dnf install dnf-automatic && systemctl enable --now dnf-automatic.timer",
        "fixable": False,
        "pkg": None,
    }


# ---------- 部署的软件漏洞 ----------

def _sw_check(name, title, ver_args, pkg):
    """单个软件版本比对：二进制存在即与源仓库候选版本比较。"""
    if not _is_linux():
        return None
    if not has_cmd(name):
        return None  # 未部署，跳过
    installed = _bin_version(name, ver_args)
    if not installed:
        return {
            "id": "sw_" + name, "group": "部署的软件漏洞",
            "title": title, "ok": None, "critical": False,
            "current": "已安装（版本不可识别）",
            "expected": "保持最新版本并关注官方安全公告",
            "advice": "版本无法自动识别，请手动核对：" + (f"对应包名 {pkg}" if pkg else ""),
            "fixable": False, "fix_scope": None, "pkg": pkg,
        }
    candidate = _pkg_candidate(pkg) if pkg else None
    if candidate is None:
        return {
            "id": "sw_" + name, "group": "部署的软件漏洞",
            "title": title, "ok": None, "critical": False,
            "current": f"已安装 {installed}",
            "expected": "保持最新版本并关注官方安全公告",
            "advice": f"非包管理器来源（如脚本安装），请关注官方安全公告并手动升级 {title}",
            "fixable": False, "fix_scope": None, "pkg": pkg,
        }
    outdated = False
    try:
        def _num(s):
            return [int(x) for x in re.findall(r"\d+", s)]
        iv = _num(installed)
        cv = _num(candidate)
        if iv and cv:
            outdated = iv < cv
    except Exception:
        outdated = False
    return {
        "id": "sw_" + name, "group": "部署的软件漏洞",
        "title": title, "critical": outdated,
        "ok": not outdated,
        "current": f"{installed} → 仓库 {candidate}",
        "expected": f"{title} 为源仓库最新版本（{candidate}）",
        "advice": f"包管理器升级：{CORE_PKG.detect()} 升级 {pkg or name}；如面板环境（nginx/caddy）可在对应插件页重装",
        "fixable": outdated,
        "fix_scope": "package" if outdated else None,
        "pkg": pkg or name,
    }


def _sw_all():
    items = []
    for name, title, ver_args, pkg in _SOFTWARE:
        try:
            it = _sw_check(name, title, ver_args, pkg)
        except Exception:
            it = None
        if it:
            items.append(it)
    return items


# ---------- 对外接口 ----------

def status():
    """插件状态：无二进制部署，提供系统与部署软件漏洞检测能力。"""
    return {
        "installed": True, "binary": "",
        "version": "plugin", "readonly": False,
        "linux": _is_linux(),
        "pm": CORE_PKG.detect(),
        "software_count": len(_SOFTWARE),
        "reports_dir": hostsec.REPORTS_DIR,
    }


def check():
    """运行全部漏洞检测，写入共享报告，返回汇总。纯只读查询。"""
    checks = []
    for fn in (_sys_security_updates, _sys_all_updates, _sys_reboot,
               _sys_unattended, _sw_all):
        try:
            r = fn()
        except Exception as e:
            r = None
        if isinstance(r, list):
            checks += r
        elif r:
            checks.append(r)
    ok = sum(1 for c in checks if c.get("ok"))
    fail = sum(1 for c in checks if c.get("ok") is False)
    skip = sum(1 for c in checks if c.get("ok") is None)
    critical = [c["id"] for c in checks
                if c.get("critical") and c.get("ok") is False]
    fixable = [c["id"] for c in checks if c.get("fixable")]
    result = {
        "tool": TOOL, "ok": ok, "fail": fail, "skipped": skip,
        "checks": checks, "critical": critical, "fixable": fixable,
        "summary": f"通过 {ok} / 存在漏洞 {fail} / 无法判定 {skip} 项",
    }
    rid = hostsec.save_report(TOOL, result)
    return {"report_id": rid, **result}


def fix(scope="security", pkg=None):
    """执行修复：按包管理器安装安全补丁 / 升级指定软件。

    scope:
      - "security": 仅安全更新（apt --only-upgrade 安全通道 / dnf upgrade --security /
        yum update --security / zypper patch / apk upgrade / pacman -Syu）；
      - "package": 升级单个软件（pkg 参数），如 nginx / caddy / redis-server；
      - "all": 全部待更新包升级。
    返回 {ok, summary, detail}。
    """
    scope = (scope or "security").strip().lower()
    if scope not in ("security", "package", "all"):
        raise AppError("修复范围需为 security / package / all")
    pm = CORE_PKG.detect()
    if not pm:
        raise AppError("未检测到受支持的包管理器（apt-get/dnf/yum/apk/zypper/pacman）")
    if scope == "package":
        if not pkg:
            raise AppError("缺少要升级的软件包名")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._:-]*", str(pkg)):
            raise AppError("软件包名格式无效")
        cmd = {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", pkg],
            "dnf": ["dnf", "upgrade", "-y", pkg],
            "yum": ["yum", "update", "-y", pkg],
            "apk": ["apk", "add", "-u", pkg],
            "zypper": ["zypper", "--non-interactive", "update", pkg],
            "pacman": ["pacman", "-S", "--noconfirm", pkg],
        }[pm]
        label = f"升级 {pkg}"
    elif scope == "all":
        cmd = {
            "apt": ["apt-get", "upgrade", "-y"],
            "dnf": ["dnf", "upgrade", "-y"],
            "yum": ["yum", "update", "-y"],
            "apk": ["apk", "upgrade"],
            "zypper": ["zypper", "--non-interactive", "update"],
            "pacman": ["pacman", "-Syu", "--noconfirm"],
        }[pm]
        label = "全部待更新包升级"
    else:  # security
        if pm == "apt":
            # 仅升级安全通道内的包，避免全量升级引入兼容风险
            r = _qrun(["sh", "-c",
                       "apt-get -s upgrade 2>/dev/null | grep -E 'Inst .*\\(.*security.*\\)' | awk '{print $2}'"],
                      timeout=40)
            pkgs = (r[1] or "").split() if r else []
            if not pkgs:
                return {"ok": True, "summary": "无待安装的安全更新", "detail": "", "pm": pm}
            cmd = ["apt-get", "install", "--only-upgrade", "-y"] + pkgs
            label = f"安全更新（{len(pkgs)} 个包）"
        elif pm == "dnf":
            cmd = ["dnf", "upgrade", "--security", "-y"]
            label = "安全更新（dnf --security）"
        elif pm == "yum":
            cmd = ["yum", "update", "--security", "-y"]
            label = "安全更新（yum --security）"
        elif pm == "zypper":
            cmd = ["zypper", "--non-interactive", "patch"]
            label = "安全补丁（zypper patch）"
        elif pm == "apk":
            cmd = ["apk", "upgrade"]
            label = "全部升级（Alpine 无独立安全通道）"
        elif pm == "pacman":
            cmd = ["pacman", "-Syu", "--noconfirm"]
            label = "全部升级（Arch 无独立安全通道）"
    r = _qrun(cmd, timeout=1800)
    rc, out, err = r if r else (-1, "", "命令执行失败")
    ok = rc == 0
    detail = (err or out or "").strip()[-2000:]
    return {
        "ok": ok, "pm": pm, "scope": scope, "pkg": pkg,
        "summary": (f"{label} 完成" if ok else f"{label} 失败（exit {rc}）"),
        "detail": detail,
    }


def reports():
    return [item for item in hostsec.reports() if item.get("tool") == TOOL]


def report(rid):
    data = hostsec.report(rid)
    if data.get("tool") != TOOL:
        raise AppError("报告不属于漏洞检测")
    return data


__all__ = ["TOOL", "status", "check", "fix", "reports", "report"]
