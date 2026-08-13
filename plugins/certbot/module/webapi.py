"""certbot 插件 Web 路由（APIRouter，由核心自动挂载到 /api）。"""

from fastapi import APIRouter, Depends

from ...web.websec import require_auth
from . import api as core

router = APIRouter()


@router.get("/certbot/status")
def certbot_status(auth=Depends(require_auth)):
    return core.status()


@router.post("/certbot/install")
def certbot_install(auth=Depends(require_auth)):
    return core.install()


@router.post("/certbot/issue")
def certbot_issue(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return core.request_cert(b.get("domain", ""), b.get("email", ""))


@router.post("/certbot/renew")
def certbot_renew(auth=Depends(require_auth)):
    return core.renew()
