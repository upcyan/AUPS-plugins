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


@router.post("/nginx/remove")
def nginx_remove(auth=Depends(require_auth)):
    return core.remove()

@router.get("/nginx/config")
def nginx_config(auth=Depends(require_auth)): return core.show()
@router.post("/nginx/validate")
def nginx_validate(auth=Depends(require_auth)): return core.validate()
@router.post("/nginx/reload")
def nginx_reload(auth=Depends(require_auth)): return core.reload()
@router.get("/nginx/logs")
def nginx_logs(kind: str = "access", limit: int = 200, auth=Depends(require_auth)): return core.logs(kind, limit)
