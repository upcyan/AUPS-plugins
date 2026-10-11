"""remotedebug 插件 CLI：build(sub) 注册命令组，run(a) 派发。

只读命令（status/catalog/audit）免 root；建会话、吊销、执行属敏感操作，要求 root。
"""

import argparse

from ...util import print_json
from . import runner as RUN
from . import store as ST

READ_ONLY = {
    "remotedebug": {"status", "catalog", "sessions", "audit"},
}


def build(sub):
    t = sub.add_parser("remotedebug", help="远程调试（只读命令通道）")
    ts = t.add_subparsers(dest="action", required=True)
    ts.add_parser("status", help="框架状态与命令目录").add_argument("--json", action="store_true")
    ts.add_parser("catalog", help="只读命令目录").add_argument("--json", action="store_true")
    ts.add_parser("sessions", help="有效调试会话").add_argument("--json", action="store_true")
    ts.add_parser("audit", help="审计记录").add_argument("--json", action="store_true")

    c = ts.add_parser("open", help="开放限时调试会话（返回一次性令牌）")
    c.add_argument("--label", default="调试会话")
    c.add_argument("--ttl", type=int, default=ST.DEFAULT_TTL,
                   help=f"有效秒数（{ST.MIN_TTL}-{ST.MAX_TTL}）")
    c.add_argument("--roots", nargs="*", default=[],
                   help="允许访问的目录（默认面板相关目录）")
    c.add_argument("--commands", nargs="*", default=[],
                   help="本次只开放这些命令（默认全部只读目录）")
    c.add_argument("--json", action="store_true")

    r = ts.add_parser("revoke", help="吊销会话")
    r.add_argument("sid")
    ts.add_parser("revoke-all", help="吊销全部会话").add_argument("--json", action="store_true")

    e = ts.add_parser("run", help="以指定会话执行只读命令")
    e.add_argument("--sid-token", required=True, help="open 返回的令牌")
    e.add_argument("command", help="命令或（多行）只读脚本")
    e.add_argument("--json", action="store_true")


def run(a):
    if a.action == "status":
        data = {"mode": "read-only", "catalog": RUN.catalog(),
                "environment": RUN.environment(),
                "min_ttl": ST.MIN_TTL, "max_ttl": ST.MAX_TTL,
                "sessions": len(ST.list_sessions())}
    elif a.action == "catalog":
        data = RUN.catalog()
    elif a.action == "sessions":
        data = {"sessions": ST.list_sessions()}
    elif a.action == "audit":
        data = {"audit": ST.audit_log()}
    elif a.action == "open":
        data = ST.create_session(label=a.label, ttl_seconds=a.ttl,
                                 roots=a.roots, commands=a.commands)
    elif a.action == "revoke":
        data = ST.revoke_session(a.sid)
    elif a.action == "revoke-all":
        data = ST.revoke_all()
    elif a.action == "run":
        session = ST.verify_token(a.sid_token)
        if session is None:
            raise SystemExit("调试令牌无效、已过期或已吊销")
        roots = [r for r in (session.get("roots") or []) if r]
        if not roots:
            from .api import _default_roots
            roots = _default_roots()
        try:
            data = RUN.execute(a.command, roots=roots,
                               allowed_bins=session.get("commands") or None)
        except Exception as e:
            ST.record_audit(session, command=a.command, ok=False, note=str(e))
            raise SystemExit(str(e))
        ST.record_audit(session, command=a.command, ok=data["ok"],
                        exit_code=data.get("exit_code"),
                        duration_ms=data.get("duration_ms"),
                        output_bytes=data.get("output_bytes"),
                        redactions=data.get("redactions"))
    else:
        raise SystemExit("未知操作")

    if getattr(a, "json", False):
        print_json(data)
        return
    if a.action in ("open",):
        print("令牌（仅显示一次）：" + data["token"])
        print(f"会话 {data['session']['sid']}  有效至 "
              f"{data['session']['expires_at']}")
        return
    if a.action == "run":
        if data.get("stdout"):
            print(data["stdout"], end="")
        if data.get("stderr"):
            print(data["stderr"], end="")
        if data.get("redactions"):
            print(f"\n[已脱敏 {data['redactions']} 处]", end="")
        if data.get("truncated"):
            print("\n[输出已截断]", end="")
        print()
        return
    print_json(data)
