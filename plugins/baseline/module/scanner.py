"""VPS 基线检查（插件负责检查项实现，报告数据层委托核心 hostsec）。

纯只读审计：不部署软件、不改任何系统配置。检查项分四类：
- 账号与权限（UID0 / 空密码 / 可登录 shell / sudoers / 敏感文件权限 / SUID）
- 系统配置基线（密码策略 / SSH 加固 / fail2ban / 系统更新 / 自动安全更新）
- 内核与网络加固（sysctl 参数 / 防火墙状态）
- 服务与应用基线（监听端口 / 安全组件覆盖）

每项返回 {id, group, title, ok, current, expected, advice, critical}，
汇总后经 hostsec.save_report() 写入共享报告目录（tool=baseline）。
"""

import os
import re
import subprocess
from collections import OrderedDict

from ...core import hostsec
from ...core import ports as CORE_PORTS
from ...core import pkg
from ...core import rtguard
from ...core import waf
from ...core import poweruser
from ...core.util import has_cmd

TOOL = "baseline"

# 期望的内核加固参数（sysctl 名 -> (期望值, 建议)）
_KERNEL_EXPECT = OrderedDict([
    ("net.ipv4.ip_forward", ("0", "关闭 IP 转发，需转发时启用仅限转发接口")),
    ("net.ipv4.conf.all.send_redirects", ("0", "禁用发送 ICMP 重定向")),
    ("net.ipv4.conf.all.accept_redirects", ("0", "不接收 ICMP 重定向冒名路由")),
    ("net.ipv4.conf.all.accept_source_route", ("0", "禁用源路由（防欺骗）")),
    ("net.ipv4.tcp_syncookies", ("1", "开启 SYN cookies 抵御洪水")),
    ("net.ipv4.conf.all.rp_filter", ("1", "开启反向路径过滤（防 IP 欺骗）")),
])

# 不应作为可登录 shell 的系统账号 shell 列表
_NOLOGIN = {"/sbin/nologin", "/usr/sbin/nologin", "/bin/false", "/usr/bin/false",
            "/bin/true", "/usr/bin/true", "/sbin/halt", "/sbin/shutdown"}


def _read(path):
    """读取文本文件；不存在/不可读返回 None。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _stat_mode(path):
    try:
        return os.stat(path).st_mode & 0o777
    except OSError:
        return None


def _sysctl(name):
    """读取 /proc/sys 内核参数；不存在返回 None。"""
    return _read("/proc/sys/" + name.replace(".", "/")).strip() or None


def _qrun(args, timeout=15):
    """带超时执行命令，捕获一切异常返回 (rc, out, err)；命令不存在返回 None。"""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception:
        return None


def _is_linux():
    return os.name == "posix" and os.path.isdir("/proc/sys")


# ---------- 检查项 ----------

def _check_uid0():
    """UID 0 账号审计：除 root 外不应存在其它 uid=0。"""
    text = _read("/etc/passwd")
    if text is None:
        return None
    extra = [ln.split(":")[0] for ln in text.splitlines()
             if ln and not ln.startswith("#")
             and len(ln.split(":")) >= 3 and ln.split(":")[2] == "0"]
    extra = [u for u in extra if u != "root"]
    return {
        "id": "acct_uid0", "group": "账号与权限",
        "title": "UID 0 账号", "critical": True,
        "ok": not extra,
        "current": "、".join(extra) if extra else "仅 root",
        "expected": "仅 root 拥有 UID 0",
        "advice": "除 root 外不应存在 uid=0 账号：usermod 改掉其 uid，或审计其用途后删除",
    }


def _check_empty_password():
    """空密码账号检查：shadow 密码字段为空即危险。"""
    text = _read("/etc/shadow")
    if text is None:
        return None  # 非 root 或非 Linux 无法读取
    empty = []
    for ln in text.splitlines():
        parts = ln.split(":")
        if len(parts) >= 2 and parts[1] == "":
            empty.append(parts[0])
    return {
        "id": "acct_emptypwd", "group": "账号与权限",
        "title": "空密码账号", "critical": True,
        "ok": not empty,
        "current": "、".join(empty) if empty else "无",
        "expected": "无空密码账号（密码字段为空意味着无需口令即可登录）",
        "advice": "为空密码账号设置口令或锁定：passwd <账号> 或 usermod -L <账号>",
    }


def _check_login_shell():
    """可登录 shell 账号枚举：查出可交互登录的账号供人工复核。"""
    text = _read("/etc/passwd")
    if text is None:
        return None
    shells = []
    for ln in text.splitlines():
        p = ln.split(":")
        if len(p) < 7:
            continue
        sh = p[6]
        if sh not in _NOLOGIN and sh.startswith("/"):
            shells.append(f"{p[0]}→{sh}")
    return {
        "id": "acct_loginshell", "group": "账号与权限",
        "title": "可登录 shell 账号", "critical": False,
        "ok": len(shells) <= 2,  # 一般仅 root 与当前管理账号
        "current": "、".join(shells) if shells else "无",
        "expected": "仅业务需要的账号使用可登录 shell，其余为 nologin/false",
        "advice": "列出账号请人工复核；非业务账号改为：chsh -s /usr/sbin/nologin <账号>",
    }


def _check_sudoers():
    """sudoers 审计：查找 NOPASSWD 免密规则与可写文件告警。"""
    if not _is_linux():
        return None
    nopasswd = []
    allowed = []
    dirs = ["/etc/sudoers"]
    sudoers_d = "/etc/sudoers.d"
    if os.path.isdir(sudoers_d):
        dirs += [os.path.join(sudoers_d, f) for f in sorted(os.listdir(sudoers_d))]
    for path in dirs:
        text = _read(path)
        if text is None:
            continue
        for ln in text.splitlines():
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if re.search(r"\bNOPASSWD\b", s):
                nopasswd.append(f"{os.path.basename(path)}: {s}")
            if "ALL" in s and "ALL" not in s.split("=")[0:1] and "(ALL)" in s:
                allowed.append(f"{os.path.basename(path)}: {s}")
    return {
        "id": "acct_sudoers", "group": "账号与权限",
        "title": "sudoers 免密与提权规则", "critical": False,
        "ok": not nopasswd,
        "current": "、".join(nopasswd[:5]) if nopasswd else "无 NOPASSWD 规则",
        "expected": "不配置 NOPASSWD 免密；无需全权提权的账号应限制可执行命令",
        "advice": "移除 sudoers 中的 NOPASSWD；如需普通账号提权应限定命令列表且要求口令",
    }


def _check_sensitive_perms():
    """敏感文件权限：passwd/shadow/sudoers 不应全局可读/可写。"""
    if not _is_linux():
        return None
    checks = []
    for path, exp in (("/etc/passwd", "0644"), ("/etc/shadow", "0640"),
                      ("/etc/sudoers", "0440"), ("/etc/ssh/sshd_config", "0644")):
        m = _stat_mode(path)
        if m is None:
            continue
        checks.append(f"{os.path.basename(path)}={m:03o}")
    shadow_m = _stat_mode("/etc/shadow")
    bad = []
    for p in ("/etc/passwd", "/etc/sudoers", "/etc/ssh/sshd_config"):
        m = _stat_mode(p)
        if m is not None and (m & 0o022):  # 组写或全局写
            bad.append(f"{os.path.basename(p)}={m:03o}")
    shadow_bad = shadow_m is not None and (shadow_m & 0o004)  # 全局可读
    if shadow_bad:
        bad.append("shadow世界可读")
    return {
        "id": "acct_perms", "group": "账号与权限",
        "title": "敏感文件权限", "critical": shadow_bad or bool(bad),
        "ok": not bad and not shadow_bad,
        "current": ", ".join(checks) or "不可读取",
        "expected": "shadow 0640(root:shadow) 且不可全局读；其余 0644/0440 且不可组写或全局写",
        "advice": "对可写敏感文件收紧权限：chmod o-w <文件>；shadow 执行 chmod 640 /etc/shadow",
    }


def _check_suid():
    """SUID/SGID 文件清单（限常见目录，防扫描爆磁盘）。"""
    if not _is_linux():
        return None
    r = _qrun(["find", "/usr/bin", "/usr/sbin", "/bin", "/sbin",
               "/usr/local/bin", "/usr/local/sbin", "-type", "f",
               "-perm", "/4000", "-print"], timeout=20)
    if r is None:
        return None
    files = [ln for ln in (r[1] or "").splitlines() if ln.strip()]
    return {
        "id": "acct_suid", "group": "账号与权限",
        "title": "SUID/SGID 文件", "critical": False,
        "ok": len(files) <= 10,
        "current": f"{len(files)} 个：{', '.join(files[:5])}" + ("…" if len(files) > 5 else ""),
        "expected": "SUID 文件数量可控且均为已知系统程序",
        "advice": "逐项确认文件来源；确属多余的可 chmod u-s <文件> 移除 SUID 位",
    }


def _login_defs():
    return _read("/etc/login.defs") or ""


def _check_password_policy():
    """密码策略：PASS_MAX_DAYS / PASS_MIN_LEN。"""
    if not _is_linux():
        return None
    ld = _login_defs()
    m = re.search(r"^\s*PASS_MAX_DAYS\s+(\d+)", ld, re.M)
    maxday = m.group(1) if m else "未配置"
    m2 = re.search(r"^\s*PASS_MIN_LEN\s+(\d+)", ld, re.M)
    minlen = m2.group(1) if m2 else "未配置"
    okmax = maxday != "未配置" and int(maxday) <= 90
    okmin = minlen != "未配置" and int(minlen) >= 8
    return {
        "id": "sys_passwd", "group": "系统配置基线",
        "title": "密码策略（login.defs）", "critical": False,
        "ok": okmax and okmin,
        "current": f"PASS_MAX_DAYS={maxday} PASS_MIN_LEN={minlen}",
        "expected": "PASS_MAX_DAYS<=90、PASS_MIN_LEN>=8",
        "advice": "编辑 /etc/login.defs：PASS_MAX_DAYS 90、PASS_MIN_LEN 8（PAM 侧可另行加强）",
    }


def _sshd_config():
    """读取 sshd 主配置 + include 片段（排除注释）。"""
    lines = []
    for path in ("/etc/ssh/sshd_config",):
        text = _read(path)
        if text:
            lines += [ln for ln in text.splitlines() if ln.strip()]
    inc = os.path.join("/etc/ssh", "sshd_config.d")
    if os.path.isdir(inc):
        for f in sorted(os.listdir(inc)):
            text = _read(os.path.join(inc, f))
            if text:
                lines += [ln for ln in text.splitlines() if ln.strip()]
    return lines


def _sshd_setting(name, cfg):
    # include 片段应覆盖主配置：取最后出现且非注释的取值
    val = None
    for ln in cfg:
        s = ln.strip()
        if s.startswith("#") or name not in s:
            continue
        parts = s.split()
        if parts and parts[0] == name and len(parts) >= 2:
            val = parts[1].lower()
    return val


def _check_ssh():
    """SSH 加固：PermitRootLogin / PasswordAuthentication / X11Forwarding。"""
    if not _is_linux():
        return None
    cfg = _sshd_config()
    if not cfg:
        return None
    root = _sshd_setting("PermitRootLogin", cfg)
    pwd = _sshd_setting("PasswordAuthentication", cfg)
    x11 = _sshd_setting("X11Forwarding", cfg)
    bad = []
    if root and root == "yes":
        bad.append("PermitRootLogin=yes")
    if pwd and pwd == "yes":
        bad.append("PasswordAuthentication=yes")
    if x11 and x11 == "yes":
        bad.append("X11Forwarding=yes")
    return {
        "id": "sys_ssh", "group": "系统配置基线",
        "title": "SSH 加固项", "critical": True,
        "ok": not bad,
        "current": "、".join(bad) if bad
                   else f"PermitRootLogin={root or '否'} PasswordAuth={pwd or '否'} X11={x11 or '否'}",
        "expected": "禁用 root 口令直登（prohibit-password/no）、关闭密码认证、关闭 X11 转发",
        "advice": "编辑 sshd_config：PermitRootLogin prohibit-password、PasswordAuthentication no、X11Forwarding no，然后 systemctl reload ssh",
    }


def _check_fail2ban():
    """fail2ban 状态：二进制或 systemd 单元。"""
    if not _is_linux():
        return None
    bin_present = has_cmd("fail2ban-client") or has_cmd("fail2ban-server")
    unit = _qrun(["systemctl", "is-active", "fail2ban"], timeout=10)
    active = (unit and unit[1].strip() == "active") or (
        not unit and bin_present)
    return {
        "id": "sys_fail2ban", "group": "系统配置基线",
        "title": "fail2ban 防暴力破解", "critical": False,
        "ok": bool(active),
        "current": "运行中" if active else "未安装/未运行",
        "expected": "fail2ban 已安装并运行（保护 ssh 等）",
        "advice": "apt/dnf install fail2ban && systemctl enable --now fail2ban",
    }


def _check_system_updates():
    """系统待更新数量：按发行版包管理器只读查询。"""
    if not _is_linux():
        return None
    pm = pkg.detect()
    if not pm:
        return None
    count = None
    if pm == "apt":
        r = _qrun(["sh", "-c", "apt list --upgradable 2>/dev/null | tail -n +2 | wc -l"], timeout=30)
        if r: count = int(r[1].strip() or "0")
    elif pm in ("dnf", "yum"):
        r = _qrun([pm, "-q", "check-update"], timeout=60)
        if r:
            lines = [ln for ln in r[1].splitlines() if "." in ln] if r[1] else []
            count = len(lines)
    elif pm == "apk":
        r = _qrun(["apk", "list", "-u"], timeout=30)
        if r: count = len([ln for ln in (r[1] or "").splitlines() if ln.strip()])
    return {
        "id": "sys_updates", "group": "系统配置基线",
        "title": "系统待更新包", "critical": False,
        "ok": count == 0 if count is not None else None,
        "current": f"{count} 个待更新" if count is not None else "不可查询",
        "expected": "及时安装安全更新",
        "advice": "运行：apt upgrade（或 dnf/apk 对应命令）安装安全更新",
    }


def _check_unattended():
    """自动安全更新：apt 20auto-upgrades 配置。"""
    text = _read("/etc/apt/apt.conf.d/20auto-upgrades")
    if text is None:
        return None
    on = ("1" in text and "Unattended-Upgrade" in text)
    return {
        "id": "sys_unattended", "group": "系统配置基线",
        "title": "自动安全更新", "critical": False,
        "ok": bool(on),
        "current": "已启用" if on else "未启用",
        "expected": "启用 unattended-upgrades 自动安装安全更新",
        "advice": "apt install unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades",
    }


def _check_kernel():
    """内核参数加固：逐项读取比对。"""
    if not _is_linux():
        return None
    items = []
    for name, (exp, advice) in _KERNEL_EXPECT.items():
        v = _sysctl(name)
        if v is None:
            continue
        ok = v == exp
        items.append(f"{name}={v}")
        if not ok:
            return {
                "id": "kernel_sysctl", "group": "内核与网络加固",
                "title": f"内核加固：{name}", "critical": not ok,
                "ok": ok, "current": f"{name}={v}",
                "expected": f"{name}={exp}",
                "advice": advice,
            }
    return {
        "id": "kernel_sysctl", "group": "内核与网络加固",
        "title": "内核与网络加固参数", "critical": False, "ok": True,
        "current": "；".join(items) if items else "不可读取（需 /proc/sys）",
        "expected": f"全部满足：{'；'.join(f'{k}={v}' for k,(v,_) in _KERNEL_EXPECT.items())}",
        "advice": "异常项加入 /etc/sysctl.d/99-hardening.conf 并 sysctl --system 生效",
    }


def _check_firewall():
    """防火墙工具状态。"""
    if not _is_linux():
        return None
    fw = CORE_PORTS.firewall_list()
    if not fw or not fw.get("kind"):
        return {
            "id": "net_firewall", "group": "内核与网络加固",
            "title": "防火墙", "critical": True, "ok": False,
            "current": "未检测到 ufw/firewalld",
            "expected": "启用 ufw 或 firewalld 并配置放行规则",
            "advice": "apt/dnf install ufw，然后 ufw default deny incoming && ufw allow <端口>",
        }
    return {
        "id": "net_firewall", "group": "内核与网络加固",
        "title": "防火墙", "critical": False,
        "ok": fw.get("status", "").lower().find("active") >= 0
              or "inactive" not in fw.get("status", "").lower()
              or "未启用" not in fw.get("status", ""),
        "current": f"{fw.get('kind')}: {fw.get('status', '')}",
        "expected": "防火墙已启用并仅放行必要端口",
        "advice": "状态为 inactive/inactive 时启用防火墙并放行面板与业务端口",
    }


def _check_listening():
    """监听端口枚举（服务与应用基线）。"""
    if not _is_linux():
        return None
    try:
        items = CORE_PORTS.listening() or []
    except Exception:
        return None
    pub = [it for it in items if it.get("local", "").startswith(("0.0.0.0", "::", "*"))
           and it.get("port")]
    ports = "、".join(str(it.get("port")) for it in pub[:12]) if pub else "无公网监听"
    return {
        "id": "svc_listen", "group": "服务与应用基线",
        "title": "公网监听端口", "critical": False,
        "ok": len(pub) <= 4,
        "current": f"{len(pub)} 个公网端口：{ports}",
        "expected": "仅暴露必要服务；非必要服务改为绑定内网/回环",
        "advice": "非业务服务将监听地址改为 127.0.0.1 或加防火墙放行清单复核",
    }


def _check_components():
    """安全组件覆盖：WAF / 实时防护 / 安全引擎 / 权限代理 / 防火墙是否形成闭环。"""
    parts = []
    try:
        w = waf.get_config()
        parts.append(("WAF", bool(w and w.get("enabled"))))
    except Exception:
        pass
    try:
        rt = rtguard.rt_status()
        parts.append(("实时防护", bool(rt and rt.get("enabled"))))
    except Exception:
        pass
    try:
        hs = hostsec.status()
        parts.append(("安全引擎", bool(hs.get("rkhunter", {}).get("installed")
                                       or hs.get("lmd", {}).get("installed"))))
    except Exception:
        pass
    try:
        pu = poweruser.server_status()
        parts.append(("权限代理", bool(pu and pu.get("enabled"))))
    except Exception:
        pass
    on = [n for n, ok in parts if ok]
    return {
        "id": "svc_components", "group": "服务与应用基线",
        "title": "安全组件覆盖", "critical": False,
        "ok": len(parts) > 0 and len(on) >= max(1, len(parts) - 1),
        "current": f"{len(on)}/{len(parts)} 启用：" + "、".join(on) if parts else "无组件可查",
        "expected": "WAF / 实时防护 / 安全引擎 / 权限代理均可按需启用",
        "advice": "在「安全加固」页按需启用缺失组件（WAF/实时防护/安全引擎/权限代理）",
    }


# ---------- 对外接口 ----------

_CHECKS = [
    _check_uid0, _check_empty_password, _check_login_shell, _check_sudoers,
    _check_sensitive_perms, _check_suid,
    _check_password_policy, _check_ssh, _check_fail2ban,
    _check_system_updates, _check_unattended,
    _check_kernel, _check_firewall,
    _check_listening, _check_components,
]


def status():
    """插件状态：纯只读审计能力，无二进制部署。"""
    return {
        "installed": True, "binary": "",
        "version": "plugin", "readonly": True,
        "linux": _is_linux(),
        "checks_count": len(_CHECKS),
        "reports_dir": hostsec.REPORTS_DIR,
    }


def check():
    """运行全部基线检查，写入共享报告，返回汇总。"""
    checks = []
    for fn in _CHECKS:
        try:
            it = fn()
        except Exception as e:
            it = None
        if not it:
            continue  # 平台不支持或不可读：跳过，不报错
        checks.append(it)
    ok = sum(1 for c in checks if c.get("ok"))
    fail = sum(1 for c in checks if not c.get("ok"))
    skip = max(0, len(_CHECKS) - len(checks))
    critical = [c["id"] for c in checks if c.get("critical") and not c.get("ok")]
    result = {
        "tool": TOOL, "ok": ok, "fail": fail, "skipped": skip,
        "checks": checks, "critical": critical,
        "summary": f"通过 {ok} / 未通过 {fail} / 跳过 {skip} 项",
    }
    rid = hostsec.save_report(TOOL, result)
    return {"report_id": rid, **result}


def reports():
    """读取共享数据层的基线检查报告。"""
    return hostsec.reports()


def report(rid):
    """读取共享数据层的单份基线报告。"""
    return hostsec.report(rid)


__all__ = ["TOOL", "status", "check", "reports", "report"]