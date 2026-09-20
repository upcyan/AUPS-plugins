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
@router.post("/nginx/config")
def nginx_config_save(body:dict=None,auth=Depends(require_auth)):
    b=body or {}; return core.save_config(b.get("content",""), reload_=bool(b.get("reload",True)))
@router.post("/nginx/validate")
def nginx_validate(auth=Depends(require_auth)): return core.validate()
@router.post("/nginx/reload")
def nginx_reload(auth=Depends(require_auth)): return core.reload()
@router.get("/nginx/logs")
def nginx_logs(kind: str = "access", limit: int = 200, auth=Depends(require_auth)): return core.logs(kind, limit)
@router.post("/nginx/deploy")
def nginx_deploy(body:dict=None,auth=Depends(require_auth)):
    b=body or {}; return core.set_deploy_method(b.get("method","host"),b.get("runtime"))

# ---------- 站点管理 ----------

@router.get("/nginx/sites")
def nginx_sites(auth=Depends(require_auth)): return core.list_sites()
@router.post("/nginx/sites")
def nginx_site_create(body:dict=None,auth=Depends(require_auth)):
    b=body or {}
    return core.create_site(b.get("host",""), b.get("mode","reverse_proxy"),
                            b.get("target",""), b.get("extra",""), b.get("options") or {})
@router.put("/nginx/sites/{host}")
def nginx_site_update(host:str,body:dict=None,auth=Depends(require_auth)):
    b=body or {}
    return core.update_site(host, mode=b.get("mode"), target=b.get("target"),
                            extra=b.get("extra"), options=b.get("options"))
@router.delete("/nginx/sites/{host}")
def nginx_site_delete(host:str,auth=Depends(require_auth)): return core.delete_site(host)

# ---------- 下载路由 / 实例控制 ----------

@router.get("/nginx/routes")
def nginx_routes(auth=Depends(require_auth)): return core.preview()
@router.post("/nginx/instance/{action}")
def nginx_instance(action:str,auth=Depends(require_auth)): return core.instance(action)
