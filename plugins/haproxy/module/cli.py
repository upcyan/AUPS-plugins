from ...util import print_json
from . import api
READ_ONLY={'haproxy':{'status','show','logs'}}
def build(sub):
 p=sub.add_parser('haproxy',help='HAProxy 反代'); s=p.add_subparsers(dest='action',required=True)
 for n in ('status','install','validate','reload','show','logs'): s.add_parser(n)
def run(a):
 if a.pcmd!='haproxy': return
 print_json(getattr(api,a.action)())
