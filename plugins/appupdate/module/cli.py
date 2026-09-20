"""appupdate 插件 CLI：命令组构建(build)、派发(run)、只读豁免(READ_ONLY)。

核心 cli.py 的 `aups plugins <插件名>` 自动 import 本模块并调用 build/run。
零核心改动：新增插件只需提供本文件（build/run/READ_ONLY）。
"""

import argparse
import os
import time

from ... import config
from ...errors import AppError
from ...util import print_json
from . import apps
from . import downloads
from . import sshkeys
from . import storage
from . import users

# 只读命令（免 root）；其余命令要求 root
READ_ONLY = {
    "app": {"list", "versions", "latest", "backends"},
    "storage": {"usage", "apks"},
    "user": {"list"},
    "ssh": {"list"},
    "downloads": {"stats"},
}


def build(sub):
    """注册命令组：user / storage / app / ssh。"""
    # ---- user ----
    u = sub.add_parser("user", help="CI 用户管理")
    us = u.add_subparsers(dest="action", required=True)
    us.add_parser("list", help="列出已管理用户及可读写目录").add_argument("--json", action="store_true")
    uc = us.add_parser("create", help="创建 CI 用户（默认 updserver）")
    uc.add_argument("name", nargs="?", default=config.DEFAULT_USER)
    uc.add_argument("--key", help="CI 公钥（可选）")
    uc.add_argument("--comment", default="")
    ur = us.add_parser("remove", help="删除 CI 用户")
    ur.add_argument("name")
    du = us.add_parser("dir", help="目录读写授权")
    dus = du.add_subparsers(dest="dir_action", required=True)
    da = dus.add_parser("add"); da.add_argument("name"); da.add_argument("path")
    dr = dus.add_parser("remove"); dr.add_argument("name"); dr.add_argument("path")
    dl = dus.add_parser("list"); dl.add_argument("name"); dl.add_argument("--json", action="store_true")

    # ---- storage ----
    st = sub.add_parser("storage", help="APK 安装包存储占用")
    sts = st.add_subparsers(dest="action", required=True)
    sts.add_parser("usage").add_argument("--json", action="store_true")
    sts.add_parser("apks").add_argument("--json", action="store_true")
    sd = sts.add_parser("delete", help="删除旧 APK（仅限站点目录下 *.apk）")
    sd.add_argument("path", nargs="+")

    # ---- app ----
    ap = sub.add_parser("app", help="多应用管理（注册中心 + 版本 + Caddy 下载路由）")
    aps = ap.add_subparsers(dest="action", required=True)
    aps.add_parser("list", help="列出已注册应用").add_argument("--json", action="store_true")
    aa = aps.add_parser("add", help="注册应用（默认目录 BASE_DIR/<名称>）")
    aa.add_argument("name")
    aa.add_argument("--dir", help="应用目录（默认 $BASE_DIR/<name>）")
    aa.add_argument("--comment", default="")
    ar = aps.add_parser("remove"); ar.add_argument("name")
    av = aps.add_parser("versions", help="列出应用下所有 APK 版本")
    av.add_argument("name")
    av.add_argument("--json", action="store_true")
    ac = aps.add_parser("caddy", help="把各应用下载路由写入反代配置并 reload")
    ac.add_argument("--preview", action="store_true", help="只打印路由，不写入")
    ac.add_argument("--no-reload", action="store_true")
    abk = aps.add_parser("backends", help="列出可用反代后端及能力（当前后端标记）")
    abk.add_argument("--json", action="store_true")
    asw = aps.add_parser("switch", help="切换默认反代后端并迁移下载路由/应用站点")
    asw.add_argument("backend", nargs="?", help="目标后端（caddy/nginx，缺省重新同步当前）")
    asw.add_argument("--no-migrate", action="store_true", help="保留旧后端路由，不清理")
    asw.add_argument("--no-reload", action="store_true")
    al = aps.add_parser("latest"); al.add_argument("name")
    aq = aps.add_parser("quota", help="查看/设置应用容量配额或全局总配额（MB，0=不限）")
    aq.add_argument("name", nargs="?")
    aq.add_argument("mb", nargs="?", type=int, help="应用配额 MB（不填则只查看）")
    aq.add_argument("--total", type=int, help="设置全局总配额 MB（0=不限）")
    aq.add_argument("--enforce", action="store_true", help="设置后立即按配额清理")
    alock = aps.add_parser("lock", help="锁定某版本，配额清理时不删除")
    alock.add_argument("name"); alock.add_argument("version")
    aunlock = aps.add_parser("unlock", help="解锁版本")
    aunlock.add_argument("name"); aunlock.add_argument("version")
    aenf = aps.add_parser("enforce", help="按配额清理最老版本（全部应用或指定）")
    aenf.add_argument("name", nargs="?")
    ad = aps.add_parser("discover", help="扫描站点目录，发现含 APK 但未注册的应用")
    ad.add_argument("--add", action="store_true", help="把全部候选项注册并打印结果")
    ad.add_argument("--json", action="store_true")

    # ---- ssh ----
    sh = sub.add_parser("ssh", help="SSH 公钥管理")
    shs = sh.add_subparsers(dest="action", required=True)
    sll = shs.add_parser("list"); sll.add_argument("user")
    sa = shs.add_parser("add"); sa.add_argument("user"); sa.add_argument("key")
    sr = shs.add_parser("remove"); sr.add_argument("user"); sr.add_argument("index", type=int)

    # ---- downloads（下载统计，原核心 `stats downloads`）----
    dl = sub.add_parser("downloads", help="下载统计（access 日志，按应用）")
    dls = dl.add_subparsers(dest="action", required=True)
    dls.add_parser("stats", help="按应用统计下载次数/独立IP").add_argument("--json", action="store_true")

    # ---- cron（定时任务：配额清理 / 下载路由自动同步）----
    cr = sub.add_parser("cron", help="定时任务（配额清理 / 下载路由自动同步）")
    cr.add_argument("job", nargs="?", choices=("quota", "routes", "all"), default="quota",
                    help="quota=每小时配额清理（默认）；routes=每10分钟路由同步；all=两者")
    cr.add_argument("--remove", action="store_true", help="移除定时任务")


def run(a):
    """按 a.pcmd（命令组）派发到具体处理器。"""
    if a.pcmd == "app":
        _app(a)
    elif a.pcmd == "storage":
        _storage(a)
    elif a.pcmd == "user":
        _user(a)
    elif a.pcmd == "ssh":
        _ssh(a)
    elif a.pcmd == "downloads":
        _downloads(a)
    elif a.pcmd == "cron":
        _cron(a)


def _user(a):
    if a.action == "list":
        data = users.list_users()
        if a.json:
            print_json(data)
        else:
            for user in data:
                print(f"■ {user['name']}  ({user['comment'] or '无备注'})")
                for d in user["dirs"]:
                    print(f"    {d}")
                if not user["dirs"]:
                    print("      (无可读写目录)")
    elif a.action == "create":
        print_json(users.create_user(a.name, a.comment, a.key))
    elif a.action == "remove":
        print_json(users.remove_user(a.name))
    elif a.action == "dir":
        if a.dir_action == "add":
            print_json(users.grant_dir(a.name, a.path))
        elif a.dir_action == "remove":
            print_json(users.revoke_dir(a.name, a.path))
        elif a.dir_action == "list":
            dirs = users.list_dir_access(a.name)
            if a.json:
                print_json(dirs)
            else:
                for d in dirs:
                    print(d)


def _storage(a):
    if a.action == "usage":
        print_json(storage.usage())
    elif a.action == "apks":
        print_json(storage.apks())
    elif a.action == "delete":
        print_json(storage.delete_apk(a.path))


def _app(a):
    if a.action == "list":
        data = apps.list_apps()
        if a.json:
            print_json(data)
            return
        if not data:
            print("(尚未注册任何应用) 示例: aups plugins appupdate app add dateforshift --dir /var/www/html/dateforshift")
            return
        for app in data:
            ver = apps.latest_version(app["name"])
            latest = ver["version"] if ver else "-"
            print(f"■ {app['name']}  ({app['comment'] or '无备注'})")
            print(f"    目录: {app['dir']}")
            print(f"    最新: {latest}")
    elif a.action == "add":
        print_json(apps.add_app(a.name, a.dir, a.comment))
    elif a.action == "remove":
        print_json(apps.remove_app(a.name))
    elif a.action == "versions":
        vs = apps.list_versions(a.name)
        if a.json:
            print_json(vs)
            return
        for v in vs:
            print(f"{v['version']:<16} {v['file']}  ({v['size_bytes']} B)")
        if not vs:
            print(f"(应用 {a.name} 目录下未发现带版本号的 APK)")
    elif a.action == "latest":
        print_json(apps.latest_version(a.name))
    elif a.action == "discover":
        found = apps.discover()
        if a.json:
            print_json(found)
            return
        if not found["candidates"]:
            print(f"(站点目录 {found['base']} 下未发现待注册的应用)")
            return
        for c in found["candidates"]:
            print(f"■ {c['name']:<20} {c['dir']}  含 {c['apk_count']} 个 APK")
        if a.add:
            for c in found["candidates"]:
                apps.add_app(c["name"], c["dir"])
            print("已全部注册，执行: aups plugins appupdate app caddy 生成下载路由")
        else:
            print("注册方式: aups plugins appupdate app add <名称> [--dir 目录]   或   aups plugins appupdate app discover --add")
    elif a.action == "quota":
        if a.total is not None:
            print_json(apps.set_total_quota(a.total))
            return
        if a.mb is None:
            if a.name:
                print_json(apps.get_app(a.name))
            else:
                print_json({"total_quota_mb": apps.get_total_quota()})
            return
        result = apps.set_quota(a.name, a.mb)
        print_json(result)
        if a.enforce:
            print_json(apps.enforce_quota(a.name))
    elif a.action == "lock":
        print_json(apps.lock_version(a.name, a.version))
    elif a.action == "unlock":
        print_json(apps.unlock_version(a.name, a.version))
    elif a.action == "enforce":
        removed = apps.enforce_quota(a.name)
        if not removed:
            print("(无需清理)")
            return
        for app, files in removed.items():
            print(f"■ {app}: 清理 {len(files)} 个文件")
            for fp in files:
                print(f"    {fp}")
    elif a.action == "caddy":
        if a.preview:
            print(apps.proxy_preview())
            return
        print_json(apps.sync_proxy_routes(reload=not a.no_reload))
    elif a.action == "backends":
        d = apps.backend_list()
        if a.json:
            print_json(d)
            return
        print(f"当前后端: {d['backend'] or '(未配置)'}")
        for b in d["backends"]:
            marks = []
            marks.append("下载路由" if b["download_route"] else "无下载路由")
            if b["clear_routes"]:
                marks.append("可迁移清理")
            cur = " ← 当前" if b["name"] == d["backend"] else ""
            print(f"  {b['name']:<10} (插件 {b['plugin']})  {' / '.join(marks)}{cur}")
        print("切换: aups plugins appupdate app switch <后端>")
    elif a.action == "switch":
        r = apps.switch_backend(a.backend, migrate=not a.no_migrate,
                                reload=not a.no_reload)
        print_json(r)


def _ssh(a):
    if a.action == "list":
        for k in sshkeys.list_keys(a.user):
            print(f"{k['index']:>2}  {k['type']:<12} {k['comment']:<28} {k['key'][:40]}")
    elif a.action == "add":
        print_json(sshkeys.add_key(a.user, a.key))
    elif a.action == "remove":
        print_json(sshkeys.remove_key(a.user, a.index))


def _downloads(a):
    d = downloads.downloads()
    if a.json:
        print_json(d)
        return
    print(f"access 日志: {d['source']}")
    print(f"独立IP来源: {'CF-Connecting-IP' if d['used_cf_header'] else 'remote_ip(受Cloudflare影响)'}")
    for app in d["apps"]:
        print(f"  {app['name']:<20} 下载 {app['total']:<6} 独立IP {app['unique_ips']}")
    if not d["apps"]:
        print("(暂无下载记录)")


_QUOTA_CRON = "/etc/cron.d/aups-enforce-quota"
_ROUTES_CRON = "/etc/cron.d/aups-appupdate-routes"


def _cron(a):
    if a.remove:
        for path, label in ((_QUOTA_CRON, "配额清理"), (_ROUTES_CRON, "路由同步")):
            try:
                os.remove(path)
                print(f"已移除定时{label}")
            except OSError:
                print(f"(未安装定时{label})")
        return
    if a.job in ("quota", "all"):
        with open(_QUOTA_CRON, "w") as f:
            f.write("0 * * * * root /usr/local/bin/aups plugins appupdate app enforce >/dev/null 2>&1\n")
        os.chmod(_QUOTA_CRON, 0o600)
        print(f"已安装每小时配额清理: {_QUOTA_CRON}")
    if a.job in ("routes", "all"):
        # CI 经 SSH 直传文件不经面板，路由数据块会滞后；周期同步让
        # latest/版本短链自动跟进新文件（无变化时反代侧跳过 reload）。
        with open(_ROUTES_CRON, "w") as f:
            f.write("*/10 * * * * root /usr/local/bin/aups plugins appupdate app caddy >/dev/null 2>&1\n")
        os.chmod(_ROUTES_CRON, 0o600)
        print(f"已安装每10分钟下载路由同步: {_ROUTES_CRON}")
