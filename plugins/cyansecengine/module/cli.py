"""cyansecengine 插件 CLI：命令组构建(build)、派发(run)、只读豁免(READ_ONLY)。

核心 cli.py 的 `aups plugins cyansecengine` 自动 import 本模块并调用 build/run。
"""

import argparse

from ... import config
from ...errors import AppError
from ...util import print_json
from . import scanner
from . import subscribe

# 只读命令（免 root）；其余命令要求 root
READ_ONLY = {
    "sec": {"status", "reports", "quarantine", "subscribe"},
}


def build(sub):
    """注册命令组：sec（安全加固）。"""
    s = sub.add_parser("sec", help="安全加固（rkhunter / LMD / YARA / 规则订阅）")
    ss = s.add_subparsers(dest="action", required=True)

    ss.add_parser("status", help="各引擎安装状态").add_argument("--json", action="store_true")

    inst = ss.add_parser("install", help="安装引擎")
    inst.add_argument("tool", choices=("rkhunter", "lmd", "yara"))

    sc = ss.add_parser("scan", help="运行扫描")
    sc.add_argument("tool", choices=("rkhunter", "lmd", "yara"))
    sc.add_argument("paths", nargs="*", help="要扫描的路径（默认面板数据目录等）")
    sc.add_argument("--no-quarantine", action="store_true", help="LMD 扫描不自动隔离")

    ss.add_parser("reports", help="历史扫描报告").add_argument("--json", action="store_true")
    rep = ss.add_parser("report", help="查看单份报告")
    rep.add_argument("rid")

    ss.add_parser("quarantine", help="隔离区文件列表").add_argument("--json", action="store_true")
    qr = ss.add_parser("restore", help="恢复隔离文件")
    qr.add_argument("name")

    ss.add_parser("subscribe", help="订阅列表").add_argument("--json", action="store_true")
    sadd = ss.add_parser("sub-add", help="添加订阅")
    sadd.add_argument("url")
    sadd.add_argument("--name", default="")
    sadd.add_argument("--interval", type=int, default=86400)
    srem = ss.add_parser("sub-remove", help="删除订阅")
    srem.add_argument("url")
    ssync = ss.add_parser("sub-sync", help="立即同步订阅规则")
    ssync.add_argument("--url", default="")
    ssync.add_argument("--due", action="store_true", help="仅同步到期订阅")


def run(a):
    """按 a.pcmd（命令组）派发。"""
    if a.pcmd == "sec":
        _sec(a)


def _sec(a):
    if a.action == "status":
        d = scanner.status()
        if a.json:
            print_json(d)
            return
        for tool, st in d.items():
            if tool in ("rules", "reports_dir"):
                continue
            flag = "已安装" if st.get("installed") else "未安装"
            print(f"{tool:<10} {flag}  {st.get('version') or ''}".rstrip())
        print(f"规则文件: {d['rules']['count']} 个  →  {d['rules']['dir']}")
    elif a.action == "install":
        print_json(scanner.install(a.tool))
    elif a.action == "scan":
        print_json(scanner.scan(a.tool, a.paths or None, quarantine=not a.no_quarantine))
    elif a.action == "reports":
        print_json(scanner.reports() if a.json else _human_reports(scanner.reports()))
    elif a.action == "report":
        print_json(scanner.report(a.rid))
    elif a.action == "quarantine":
        items = scanner.quarantine_list()
        print_json(items if a.json else _human_quarantine(items))
    elif a.action == "restore":
        print_json(scanner.quarantine_restore(a.name))
    elif a.action == "subscribe":
        subs = subscribe.list_subs()
        print_json(subs if a.json else _human_subs(subs))
    elif a.action == "sub-add":
        print_json(subscribe.add_sub(a.url, a.name, a.interval))
    elif a.action == "sub-remove":
        print_json(subscribe.remove_sub(a.url))
    elif a.action == "sub-sync":
        print_json(subscribe.sync(a.url or None, due_only=a.due))


def _human_reports(reports):
    if not reports:
        return "(暂无报告)"
    return "\n".join(f"{r['ts']}  {r['tool']:<10} {r['summary']}" for r in reports)


def _human_quarantine(items):
    if not items:
        return "(隔离区为空)"
    return "\n".join(f"{i['name']}  ({i['size']} B)" for i in items)


def _human_subs(subs):
    if not subs:
        return "(无订阅)"
    lines = []
    for s in subs:
        state = "启用" if s.get("enabled") else "停用"
        last = (__import__("time").strftime("%F %T", __import__("time").localtime(s["last_sync"]))
                if s.get("last_sync") else "未同步")
        lines.append(f"■ {s.get('name', s['url'])}  [{state}]  规则 {s.get('rule_count', 0)}  上次 {last}")
        lines.append(f"    {s['url']}")
    return "\n".join(lines)
