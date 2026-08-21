"""原生安全组插件 API。核心安全组页也会通过 firewall provider 接口调用。"""

from fastapi import APIRouter, Depends

from ...core import pkg
from ...web.websec import require_admin, require_auth
from . import firewall

router = APIRouter()


@router.get("/secgroup/status")
def secgroup_status(auth=Depends(require_auth)):
    return firewall.status()


@router.post("/secgroup/open")
def secgroup_open(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    return firewall.open_port(b.get("port"), b.get("protocol"), b.get("source"), b.get("pwd"))


@router.post("/secgroup/close")
def secgroup_close(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    return firewall.close_port(b.get("port"), b.get("protocol"), b.get("source"), b.get("pwd"))


def post_install():
    if not firewall.status().get("installed"):
        pkg.install(["nftables"])
    return firewall.start()


start = firewall.start
stop = firewall.stop
remove = firewall.remove
