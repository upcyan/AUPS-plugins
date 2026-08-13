"""certbot 插件 CLI：build/run/READ_ONLY。

命令组：certbot（状态/安装/申请证书/续期）。
"""

from ...util import print_json
from . import api

READ_ONLY = {
    "certbot": {"status"},
}


def build(sub):
    cb = sub.add_parser("certbot", help="Certbot 证书签发（状态/安装/申请/续期）")
    cbs = cb.add_subparsers(dest="action", required=True)
    cbs.add_parser("status", help="查看 certbot 状态与证书目录").add_argument("--json", action="store_true")
    cbs.add_parser("install", help="检测/安装 certbot")
    ci = cbs.add_parser("issue", help="申请证书")
    ci.add_argument("domain")
    ci.add_argument("--email", default="admin@example.com", help="Let's Encrypt 联系邮箱")
    cbs.add_parser("renew", help="续期证书")


def run(a):
    if a.pcmd != "certbot":
        return
    if a.action == "status":
        s = api.status()
        if a.json:
            print_json(s)
            return
        print(f"certbot: {'已安装' if s['installed'] else '未检测到'}  {s['version'] or ''}")
        print(f"  证书/数据目录: {s['data_dir']}")
    elif a.action == "install":
        print_json(api.install())
    elif a.action == "issue":
        print_json(api.request_cert(a.domain, a.email))
    elif a.action == "renew":
        print_json(api.renew())
