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
from . import sshkeys
from . import storage
from . import users

# 只读命令（免 root）；其余命令要求 root
READ_ONLY = {
    "app": {"list", "versions", "latest"},
    "storage": {"usage", "apks"},
    "user": {"list"},
    "ssh": {"list"},
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
    ac = aps.add_parser("caddy", help="把各应用下载路由写入 Caddyfile 并 reload")
    ac.add_argument("--preview", action="store_true", help="只打印路由，不写入")
    ac.add_argument("--no-reload", action="store_true")
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
            print(apps._caddy_preview())
            return
        print_json(apps.update_caddy_routes(reload=not a.no_reload))


def _ssh(a):
    if a.action == "list":
        for k in sshkeys.list_keys(a.user):
            print(f"{k['index']:>2}  {k['type']:<12} {k['comment']:<28} {k['key'][:40]}")
    elif a.action == "add":
        print_json(sshkeys.add_key(a.user, a.key))
    elif a.action == "remove":
        print_json(sshkeys.remove_key(a.user, a.index))
