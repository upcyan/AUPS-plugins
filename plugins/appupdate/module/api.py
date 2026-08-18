"""appupdate 插件 Web API 路由。

重要：FastAPI 按注册顺序匹配路由。静态路由必须在参数化路由之前，
否则 POST /apps/caddy 会被 GET /apps/{name} 吃掉 → 405 Method Not Allowed。
"""

from fastapi import APIRouter, Depends, HTTPException

from ...web.websec import require_auth
from . import apps as A
from . import storage as S
from . import users as U
from . import downloads as D

router = APIRouter()


# ==================== 静态路由（必须在 /{name} 之前）====================

# ---------- 应用管理 ----------
@router.get("/apps")
def apps_list(auth=Depends(require_auth)):
    return {"apps": A.list_apps(), "total_quota_mb": A.get_total_quota()}


@router.post("/apps")
def apps_create(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return A.add_app(b.get("name", ""), b.get("dir"), b.get("comment", ""))


@router.post("/apps/validate-domain")
def validate_domain(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return A.validate_domain(b.get("domain", ""), b.get("workdir", ""))


@router.get("/apps/proxy-list")
def proxy_list(auth=Depends(require_auth)):
    from ... import registry
    return {"proxies": registry.capability_providers("proxy")}


@router.post("/apps/caddy")
def apps_caddy(body: dict = None, auth=Depends(require_auth)):
    return A.update_proxy_routes(bool((body or {}).get("reload", True)))


@router.get("/apps/discover")
def apps_discover(auth=Depends(require_auth)):
    return A.discover()


# ==================== 参数化路由（静态路由之后）====================

@router.delete("/apps/{name}")
def apps_delete(name: str, auth=Depends(require_auth)):
    return A.remove_app(name)


@router.get("/apps/{name}")
def apps_get(name: str, auth=Depends(require_auth)):
    return A.get_app(name)


@router.get("/apps/{name}/versions")
def apps_versions(name: str, auth=Depends(require_auth)):
    vs = A.list_versions(name)
    latest = A.latest_version(name)
    return {"name": name, "versions": vs, "latest": latest}


@router.post("/apps/{name}/versions/{version}/lock")
def app_version_lock(name: str, version: str, auth=Depends(require_auth)):
    return A.lock_version(name, version)


@router.post("/apps/{name}/versions/{version}/unlock")
def app_version_unlock(name: str, version: str, auth=Depends(require_auth)):
    return A.unlock_version(name, version)


@router.post("/apps/{name}/quota")
def app_quota_set(name: str, body: dict = None, auth=Depends(require_auth)):
    return A.set_quota(name, (body or {}).get("mb", 0))


@router.get("/apps/{name}/deploy")
def deploy_get(name: str, auth=Depends(require_auth)):
    return A.get_deploy(name)


@router.post("/apps/{name}/deploy")
def deploy_set(name: str, body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return A.set_deploy(name, **{k: v for k, v in b.items()
                                  if k in ("domain", "ssl", "port", "workdir", "user",
                                           "ci_user", "ssh_key", "comment", "proxy")})


@router.get("/apps/{name}/deploy/domain")
def deploy_domain(name: str, auth=Depends(require_auth)):
    return A.request_domain(name)


@router.get("/apps/{name}/deploy/ssl")
def deploy_ssl(name: str, auth=Depends(require_auth)):
    return A.request_ssl(name)


@router.get("/apps/{name}/deploy/port")
def deploy_port(name: str, auth=Depends(require_auth)):
    return A.request_port(name)


@router.get("/apps/{name}/deploy/workdir")
def deploy_workdir(name: str, auth=Depends(require_auth)):
    return A.request_workdir(name)


@router.get("/apps/{name}/deploy/user")
def deploy_user(name: str, auth=Depends(require_auth)):
    return A.request_user(name)


@router.get("/apps/{name}/deploy/sshkey")
def deploy_sshkey(name: str, auth=Depends(require_auth)):
    return A.request_ssh_key(name)


# ==================== 存储管理 ====================

@router.get("/storage/usage")
def storage_usage(auth=Depends(require_auth)):
    return S.usage()


@router.get("/storage/apks")
def storage_apks(auth=Depends(require_auth)):
    return S.apks()


@router.post("/storage/delete")
def storage_delete(body: dict = None, auth=Depends(require_auth)):
    return S.delete_apk((body or {}).get("paths", []))


@router.get("/storage/quota")
def storage_quota(auth=Depends(require_auth)):
    return S.quota_status()


@router.post("/storage/quota")
def storage_quota_set(body: dict = None, auth=Depends(require_auth)):
    return {"total_quota_mb": A.set_total_quota((body or {}).get("total_mb", 0))}


@router.post("/storage/enforce")
def storage_enforce(auth=Depends(require_auth)):
    return A.enforce_quota()


# ==================== CI 用户 ====================

@router.get("/users")
def users_list(auth=Depends(require_auth)):
    return {"users": U.list_users()}


@router.post("/users")
def users_create(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return U.create_user(b.get("name", ""), b.get("comment", ""), b.get("key", ""))


@router.delete("/users/{name}")
def users_delete(name: str, auth=Depends(require_auth)):
    return U.remove_user(name)


@router.get("/users/{name}/dirs")
def users_dirs(name: str, auth=Depends(require_auth)):
    return {"user": name, "dirs": U.list_dir_access(name)}


@router.post("/users/{name}/dirs")
def users_dirs_add(name: str, body: dict = None, auth=Depends(require_auth)):
    return U.grant_dir(name, (body or {}).get("path", ""))


@router.post("/users/{name}/dirs/remove")
def users_dirs_remove(name: str, body: dict = None, auth=Depends(require_auth)):
    return U.revoke_dir(name, (body or {}).get("path", ""))


# ==================== SSH 公钥 ====================

@router.get("/ssh/{user}")
def ssh_list(user: str, auth=Depends(require_auth)):
    return {"user": user, "keys": U.list_keys(user)}


@router.post("/ssh/{user}")
def ssh_add(user: str, body: dict = None, auth=Depends(require_auth)):
    return U.add_key(user, (body or {}).get("key", ""))


@router.delete("/ssh/{user}/{index}")
def ssh_remove(user: str, index: int, auth=Depends(require_auth)):
    return U.remove_key(user, index)


# ==================== 统计 ====================

@router.get("/stats/downloads")
def stats_downloads(auth=Depends(require_auth)):
    return D.downloads()
