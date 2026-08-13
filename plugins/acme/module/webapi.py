"""acme 插件 Web 路由（APIRouter，由核心自动挂载到 /api）。"""

from fastapi import APIRouter, Depends

from ...web.websec import require_auth
from . import api as core

router = APIRouter()


@router.get("/acme/status")
def acme_status(auth=Depends(require_auth)):
    return core.status()


@router.post("/acme/install")
def acme_install(auth=Depends(require_auth)):
    return core.install()


@router.post("/acme/issue")
def acme_issue(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return core.request_cert(b.get("domain", ""), b.get("email", ""))


@router.post("/acme/renew")
def acme_renew(auth=Depends(require_auth)):
    return core.renew()
