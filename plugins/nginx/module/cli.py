"""nginx 插件 CLI：命令组构建(build)、派发(run)、只读豁免(READ_ONLY)。

命令组：nginx（Nginx 反代环境状态/安装）。
"""

from ...errors import AppError
from ...util import print_json
from . import api

READ_ONLY = {
    "nginx": {"status"},
}


def build(sub):
    ng = sub.add_parser("nginx", help="Nginx 反代环境（状态/安装）")
    ngs = ng.add_subparsers(dest="action", required=True)
    ngs.add_parser("status", help="查看 nginx 状态与部署目录").add_argument("--json", action="store_true")
    ngs.add_parser("install", help="检测系统 nginx 或部署到面板 runtime 目录")


def run(a):
    if a.pcmd != "nginx":
        return
    if a.action == "status":
        s = api.status()
        if a.json:
            print_json(s)
            return
        print(f"nginx: {'已安装' if s['installed'] else '未检测到'}  {s['version'] or ''}")
        print(f"  runtime: {s['runtime_dir']}")
        print(f"  config : {s['config_dir']}")
        print(f"  data   : {s['data_dir']}")
    elif a.action == "install":
        print_json(api.install())
