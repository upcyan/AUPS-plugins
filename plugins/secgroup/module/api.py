"""原生安全组插件 API。核心安全组页也会通过 firewall provider 接口调用。"""

from fastapi import APIRouter, Depends

from ...core import pkg
from ...web.websec import require_admin, require_auth
from . import blacklist, firewall

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


@router.get("/secgroup/blacklists")
def blacklist_status(auth=Depends(require_auth)):
    return blacklist.status()


@router.post("/secgroup/blacklists")
def blacklist_save(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    kwargs = {
        "url": b.get("url"), "name": b.get("name"), "provider": b.get("provider", "generic"),
        "auth_type": b.get("auth_type"), "interval_sec": b.get("interval_sec", 3600),
        "enabled": b.get("enabled", True), "sync_now": b.get("sync_now", False),
    }
    if "token" in b:
        kwargs["token"] = b.get("token")
    return blacklist.set_subscription(**kwargs)


@router.delete("/secgroup/blacklists/{sub_id}")
def blacklist_remove(sub_id: str, auth=Depends(require_admin)):
    return blacklist.remove_subscription(sub_id)


@router.post("/secgroup/blacklists/sync")
def blacklist_sync(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    return blacklist.sync(b.get("id"), bool(b.get("due_only", False)))


@router.post("/secgroup/blacklists/schedule")
def blacklist_schedule(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    return blacklist.set_schedule(bool(b.get("enabled", False)), b.get("check_minutes", 5))


def post_install():
    if not firewall.status().get("installed"):
        pkg.install(["nftables"])
    return firewall.start()


start = firewall.start
stop = firewall.stop
remove = firewall.remove
