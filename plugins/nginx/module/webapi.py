"""nginx 插件 Web 路由（APIRouter，由核心自动挂载到 /api）。"""

from fastapi import APIRouter, Depends

from ...web.websec import require_auth
from . import api as core

router = APIRouter()


@router.get("/nginx/status")
def nginx_status(auth=Depends(require_auth)):
    return core.status()


@router.post("/nginx/install")
def nginx_install(auth=Depends(require_auth)):
    return core.install()
