"""caddy 插件 CLI：命令组构建(build)、派发(run)、只读豁免(READ_ONLY)。

caddy 插件提供 caddyconf（反代配置 + WAF）。核心 cli.py 的
`aups plugins caddy` 自动 import 本模块并调用 build/run。
"""

import argparse
import os
import time

from ... import config
from ...errors import AppError
from ...util import print_json
from . import rproxy
from . import waf

# 只读命令（免 root）；其余命令要求 root
READ_ONLY = {
    "caddyconf": {"status", "show", "preview"},
}


def build(sub):
    """注册命令组：caddyconf。"""
    cc = sub.add_parser("caddyconf", help="反代配置管理（Caddy，含 WAF 防护）")
    ccs = cc.add_subparsers(dest="action", required=True)
    ccs.add_parser("status", help="反代后端与 WAF 状态").add_argument("--json", action="store_true")
    ccs.add_parser("show", help="查看当前 Caddyfile 中的托管片段").add_argument("--json", action="store_true")
    ccs.add_parser("preview", help="预览将写入的路由与 WAF 片段").add_argument("--json", action="store_true")
    ca = ccs.add_parser("apply", help="写入 下载路由+WAF 片段 并 reload")
    ca.add_argument("--no-reload", action="store_true")
    cb = ccs.add_parser("backend", help="查看/切换反代后端（预留：Caddy 可换 nginx 等）")
    cbs = cb.add_subparsers(dest="ba", required=True)
    cbs.add_parser("list").add_argument("--json", action="store_true")
    cbset = cbs.add_parser("set", help="切换后端（写入 rproxy.json）")
    cbset.add_argument("name")
    cw = ccs.add_parser("waf", help="WAF 防护管理")
    cws = cw.add_subparsers(dest="wa", required=True)
    cws.add_parser("status").add_argument("--json", action="store_true")
    cws.add_parser("on", help="启用 WAF")
    cws.add_parser("off", help="停用 WAF")
    cws.add_parser("show", help="显示当前生效规则（本地+订阅）").add_argument("--json", action="store_true")
    wr = cws.add_parser("rule", help="本地规则管理")
    wrs = wr.add_subparsers(dest="ra", required=True)
    wrs.add_parser("list").add_argument("--json", action="store_true")
    wra = wrs.add_parser("add")
    wra.add_argument("kind", choices=("path_regex", "user_agent", "header", "method", "query"))
    wra.add_argument("pattern")
    wra.add_argument("--field", help="header/query 规则对应的字段名")
    wra.add_argument("--name", default="", help="备注")
    wrr = wrs.add_parser("remove"); wrr.add_argument("id")
    wre = wrs.add_parser("enable"); wre.add_argument("id")
    wrd = wrs.add_parser("disable"); wrd.add_argument("id")
    wi = cws.add_parser("ip", help="IP 黑/白名单")
    wis = wi.add_subparsers(dest="ia", required=True)
    wis.add_parser("list").add_argument("--json", action="store_true")
    wib = wis.add_parser("block", help="加入黑名单"); wib.add_argument("ip")
    wiu = wis.add_parser("unblock", help="移出黑名单"); wiu.add_argument("ip")
    wia = wis.add_parser("allow", help="加入白名单"); wia.add_argument("ip")
    wid = wis.add_parser("deny", help="移出白名单"); wid.add_argument("ip")
    rl = cws.add_parser("ratelimit", help="请求限流（Caddy 原生 rate_limit）")
    rls = rl.add_subparsers(dest="ra", required=True)
    rls.add_parser("off", help="关闭限流")
    rlset = rls.add_parser("set"); rlset.add_argument("requests", type=int); rlset.add_argument("window")
    su = cws.add_parser("subscribe", help="订阅远程 WAF 规则")
    sus = su.add_subparsers(dest="sa", required=True)
    sus.add_parser("status").add_argument("--json", action="store_true")
    srec = sus.add_parser("recommended", help="一键订阅内置推荐规则集（OWASP CRS 精选）")
    srec.add_argument("--interval", type=int, default=3600, help="自动同步间隔秒（默认3600）")
    suset = sus.add_parser("set", help="添加/更新订阅")
    suset.add_argument("url")
    suset.add_argument("--name", default="")
    suset.add_argument("--interval", type=int, default=3600, help="自动同步间隔秒（默认3600）")
    surem = sus.add_parser("remove"); surem.add_argument("url")
    susync = sus.add_parser("sync", help="立即拉取订阅规则（可指定 url）")
    susync.add_argument("url", nargs="?")
    susync.add_argument("--due", action="store_true", help="只同步已到期订阅（供定时任务用）")
    scron = sus.add_parser("cron", help="安装/移除自动同步定时任务（按各订阅间隔）")
    scron.add_argument("--remove", action="store_true", help="移除定时任务")


def run(a):
    """按 a.pcmd（命令组）派发。"""
    if a.pcmd == "caddyconf":
        _caddyconf(a)


def _caddyconf(a):
    if a.action == "status":
        s = rproxy.status()
        if a.json:
            print_json(s)
            return
        print(f"反代后端: {s['backend']}")
        if s.get("name") == "caddy":
            print(f"Caddy: {s.get('version') or '(未知版本)'}  reload: {s.get('reload_method') or '-'}")
        print(f"配置: {s.get('caddyfile')}  {'存在' if s.get('exists') else '不存在'}")
        print(f"WAF: {'已启用' if s.get('waf_enabled') else '已停用'}")
        if s.get("name") == "caddy" and s.get("exists") and not s.get("reload_method"):
            print("[提示] 未检测到 systemctl/caddy，apply 后无法 reload")
    elif a.action == "show":
        d = rproxy.show()
        if a.json:
            print_json(d)
            return
        print(f"配置文件: {d['caddyfile']}（{d['total_lines']} 行）")
        for sec, txt in d["managed"].items():
            print(f"\n===== {sec} =====")
            print(txt if txt.strip() else "(空)")
    elif a.action == "preview":
        d = rproxy.preview()
        if a.json:
            print_json(d)
            return
        for sec, txt in d.items():
            print(f"===== {sec} =====")
            print(txt)
    elif a.action == "apply":
        print_json(rproxy.apply(reload=not a.no_reload))
    elif a.action == "backend":
        if a.ba == "list":
            print_json(rproxy.backend_list())
        elif a.ba == "set":
            print_json(rproxy.set_backend(a.name))
    elif a.action == "waf":
        _caddyconf_waf(a)


def _caddyconf_waf(a):
    if a.wa == "status":
        cfg = waf.get_config()
        if a.json:
            print_json(cfg)
            return
        rl = cfg["rate_limit"]
        print(f"WAF: {'已启用' if cfg['enabled'] else '已停用'}")
        print(f"黑名单: {', '.join(cfg['blacklist_ips']) or '(空)'}")
        print(f"白名单: {', '.join(cfg['whitelist_ips']) or '(空)'}")
        rl_state = f"开启 {rl['requests']} 次/{rl['window']}" if rl["enabled"] else "关闭"
        print(f"限流: {rl_state}")
        print(f"本地规则: {len(cfg['rules'])} 条   订阅源: {len(cfg['subscriptions'])} 个")
        print("生效规则一览: aups plugins caddy caddyconf waf show    应用: aups plugins caddy caddyconf apply")
    elif a.wa == "on":
        print_json(waf.set_enabled(True))
    elif a.wa == "off":
        print_json(waf.set_enabled(False))
    elif a.wa == "show":
        r = waf.render_config()
        if a.json:
            print_json(r)
            return
        print(f"WAF 生效规则（{len(r['rules'])} 条）")
        for rl in r["rules"]:
            field = f" [{rl['field']}]" if rl.get("field") else ""
            print(f"  - {rl['kind']}{field} {rl['pattern']}")
        if r["blacklist_ips"]:
            print("黑名单: " + ", ".join(r["blacklist_ips"]))
        if r["whitelist_ips"]:
            print("白名单: " + ", ".join(r["whitelist_ips"]))
        if r["rate_limit"].get("enabled"):
            print(f"限流: {r['rate_limit']['requests']}次/{r['rate_limit']['window']}")
    elif a.wa == "rule":
        _caddyconf_waf_rule(a)
    elif a.wa == "ip":
        _caddyconf_waf_ip(a)
    elif a.wa == "ratelimit":
        _caddyconf_waf_ratelimit(a)
    elif a.wa == "subscribe":
        _caddyconf_waf_subscribe(a)


def _caddyconf_waf_rule(a):
    if a.ra == "list":
        rules = waf.get_config()["rules"]
        if a.json:
            print_json(rules)
            return
        if not rules:
            print("(暂无本地规则)  添加: aups plugins caddy caddyconf waf rule add <kind> <pattern> [--field 头名] [--name 备注]")
            return
        for r in rules:
            st = "启用" if r["enabled"] else "停用"
            field = f" [{r['field']}]" if r.get("field") else ""
            print(f"{r['id']:<14} {st}  {r['kind']:<10}{field} {r['pattern']}  {r.get('name','')}")
    elif a.ra == "add":
        print_json(waf.add_rule(a.kind, a.pattern, a.field, a.name))
    elif a.ra == "remove":
        print_json(waf.remove_rule(a.id))
    elif a.ra == "enable":
        print_json(waf.set_rule_enabled(a.id, True))
    elif a.ra == "disable":
        print_json(waf.set_rule_enabled(a.id, False))


def _caddyconf_waf_ip(a):
    if a.ia == "list":
        cfg = waf.get_config()
        if a.json:
            print_json({"blacklist": cfg["blacklist_ips"], "whitelist": cfg["whitelist_ips"]})
            return
        print("黑名单: " + (", ".join(cfg["blacklist_ips"]) or "(空)"))
        print("白名单: " + (", ".join(cfg["whitelist_ips"]) or "(空)"))
        print("命令: block/unblock 管理黑名单，allow/deny 管理白名单")
    elif a.ia == "block":
        print_json(waf.add_ip("blacklist", a.ip))
    elif a.ia == "unblock":
        print_json(waf.remove_ip("blacklist", a.ip))
    elif a.ia == "allow":
        print_json(waf.add_ip("whitelist", a.ip))
    elif a.ia == "deny":
        print_json(waf.remove_ip("whitelist", a.ip))


def _caddyconf_waf_ratelimit(a):
    if a.ra == "off":
        print_json(waf.set_rate_limit(False))
    elif a.ra == "set":
        print_json(waf.set_rate_limit(True, a.requests, a.window))


def _caddyconf_waf_subscribe(a):
    if a.sa == "status":
        subs = waf.get_config()["subscriptions"]
        if a.json:
            print_json(subs)
            return
        if not subs:
            print("(未配置订阅)  添加: aups plugins caddy caddyconf waf subscribe set <URL> [--interval 秒]")
            return
        for s in subs:
            state = "启用" if s["enabled"] else "停用"
            last = (time.strftime("%F %T", time.localtime(s["last_fetch"]))
                    if s.get("last_fetch") else "未同步")
            print(f"■ {s['url']}")
            print(f"    名称: {s['name']}  状态: {state}  间隔: {s['interval_sec']}s  "
                  f"规则: {s['rule_count']}  上次同步: {last}")
            if s.get("last_error"):
                print(f"    上次错误: {s['last_error']}")
    elif a.sa == "set":
        print_json(waf.subscribe_set(a.url, a.name, a.interval))
    elif a.sa == "recommended":
        print_json(waf.subscribe_recommended(a.interval))
    elif a.sa == "remove":
        print_json(waf.subscribe_remove(a.url))
    elif a.sa == "sync":
        print_json(waf.subscribe_sync(a.url, due_only=a.due))
    elif a.sa == "cron":
        _waf_subscribe_cron(a.remove)


def _waf_subscribe_cron(remove=False):
    path = "/etc/cron.d/aups-waf-sync"
    if remove:
        try:
            os.remove(path)
            print("已移除订阅自动同步定时任务")
        except OSError:
            print("(未安装)")
        return
    cron = ("*/5 * * * * root /usr/local/bin/aups plugins caddy caddyconf waf subscribe sync "
            "--due >/dev/null 2>&1\n")
    with open(path, "w") as f:
        f.write(cron)
    os.chmod(path, 0o600)
    print(f"已安装订阅自动同步定时任务（每5分钟检查到期订阅）: {path}")
