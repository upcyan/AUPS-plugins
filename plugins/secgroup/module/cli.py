"""原生安全组插件 CLI。"""

from ...core.util import print_json
from . import blacklist, firewall

READ_ONLY = {"secgroup": {"status", "blacklist-list"}}


def build(sub):
    group = sub.add_parser("secgroup", help="原生安全组与黑名单订阅")
    actions = group.add_subparsers(dest="action", required=True)
    actions.add_parser("status", help="查看安全组状态").add_argument("--json", action="store_true")
    actions.add_parser("blacklist-list", help="查看黑名单订阅").add_argument("--json", action="store_true")
    sync = actions.add_parser("blacklist-sync", help="同步黑名单订阅")
    sync.add_argument("--id", default=None, help="仅同步指定订阅 ID")
    sync.add_argument("--due", action="store_true", help="仅同步已到期订阅")


def run(args):
    if args.action == "status":
        print_json(firewall.status())
    elif args.action == "blacklist-list":
        print_json(blacklist.status())
    elif args.action == "blacklist-sync":
        print_json(blacklist.sync(args.id, args.due))
