"""青·擎统一安全 API。"""

from fastapi import APIRouter, Depends

from ...web.websec import require_admin, require_auth
from . import firewall, security

router = APIRouter()


@router.get("/cyansecengine/status")
def cyan_status(auth=Depends(require_auth)):
    return security.status()


@router.post("/cyansecengine/check")
def cyan_check(auth=Depends(require_admin)):
    return security.check()


@router.post("/cyansecengine/waf")
def cyan_waf(body: dict = None, auth=Depends(require_admin)):
    return security.waf_update(body)


@router.post("/cyansecengine/realtime")
def cyan_realtime(body: dict = None, auth=Depends(require_admin)):
    return security.realtime_update(body)


@router.post("/cyansecengine/firewall/open")
def cyan_firewall_open(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    return firewall.open_port(b.get("port"), b.get("protocol", "tcp"), b.get("source"), b.get("pwd"))


@router.post("/cyansecengine/firewall/close")
def cyan_firewall_close(body: dict = None, auth=Depends(require_admin)):
    b = body or {}
    return firewall.close_port(b.get("port"), b.get("protocol", "tcp"), b.get("source"), b.get("pwd"))
