"""acme.sh 插件 CLI：build/run/READ_ONLY。

命令组：acme（状态/安装/申请证书/续期）。
"""

from ...util import print_json
from . import api

READ_ONLY = {
    "acme": {"status"},
}


def build(sub):
    am = sub.add_parser("acme", help="acme.sh 证书签发（状态/安装/申请/续期）")
    ams = am.add_subparsers(dest="action", required=True)
    ams.add_parser("status", help="查看 acme.sh 状态与目录").add_argument("--json", action="store_true")
    ams.add_parser("install", help="部署 acme.sh 到面板 runtime 目录")
    ai = ams.add_parser("issue", help="申请证书")
    ai.add_argument("domain")
    ai.add_argument("--email", default="", help="账号邮箱")
    ams.add_parser("renew", help="续期证书")


def run(a):
    if a.pcmd != "acme":
        return
    if a.action == "status":
        s = api.status()
        if a.json:
            print_json(s)
            return
        print(f"acme.sh: {'已安装' if s['installed'] else '未安装'}  {s['version'] or ''}")
        print(f"  脚本: {s['bin']}")
        print(f"  证书/数据目录: {s['data_dir']}")
    elif a.action == "install":
        print_json(api.install())
    elif a.action == "issue":
        print_json(api.request_cert(a.domain, a.email))
    elif a.action == "renew":
        print_json(api.renew())
