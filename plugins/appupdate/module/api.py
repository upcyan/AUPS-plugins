"""appupdate 插件 Web API 路由（由核心自动挂载，前缀 /api）。

核心 create_app() 扫描 registry 里启用插件的 manifest["api_module"] 并 include_router。
鉴权用核心 websec.require_auth（FastAPI 依赖），无需改动核心即可新增路由。
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from ...web.websec import require_auth
from . import apps as A
from . import downloads as DL
from . import sshkeys as S
from . import storage as ST
from . import users as U

router = APIRouter()


# ---------- 存储 ----------
@router.get("/storage/usage")
def storage_usage(auth=Depends(require_auth)):
    return ST.usage()


@router.get("/storage/apks")
def storage_apks(auth=Depends(require_auth)):
    return {"apks": ST.apks()}


@router.post("/storage/delete")
def storage_delete(body: dict = None, auth=Depends(require_auth)):
    return {"deleted": ST.delete_apk((body or {}).get("paths", []))}


@router.get("/storage/quota")
def storage_quota(auth=Depends(require_auth)):
    return ST.quota_status()


@router.post("/storage/quota")
def storage_quota_set(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    if "total_mb" in b:
        A.set_total_quota(b["total_mb"])
    return ST.quota_status()


@router.post("/storage/enforce")
def storage_enforce(auth=Depends(require_auth)):
    return A.enforce_quota()


# ---------- 应用 ----------
@router.get("/apps")
def apps_list(auth=Depends(require_auth)):
    return {"apps": A.list_apps()}


@router.post("/apps")
def apps_create(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return A.add_app(b.get("name", ""), b.get("dir"), b.get("comment", ""))


@router.delete("/apps/{name}")
def apps_delete(name: str, auth=Depends(require_auth)):
    return A.remove_app(name)


@router.get("/apps/{name}/versions")
def apps_versions(name: str, auth=Depends(require_auth)):
    return {"versions": A.list_versions(name), "latest": A.latest_version(name)}


@router.post("/apps/caddy")
def apps_caddy(auth=Depends(require_auth)):
    return A.update_caddy_routes()


@router.get("/apps/discover")
def apps_discover(auth=Depends(require_auth)):
    return A.discover()


@router.post("/apps/{name}/quota")
def app_quota_set(name: str, body: dict = None, auth=Depends(require_auth)):
    return A.set_quota(name, (body or {}).get("mb", 0))


@router.post("/apps/{name}/versions/{version}/lock")
def app_version_lock(name: str, version: str, auth=Depends(require_auth)):
    return A.lock_version(name, version)


@router.post("/apps/{name}/versions/{version}/unlock")
def app_version_unlock(name: str, version: str, auth=Depends(require_auth)):
    return A.unlock_version(name, version)


# ---------- CI 用户 ----------
@router.get("/users")
def users_list(auth=Depends(require_auth)):
    return {"users": U.list_users()}


@router.post("/users")
def users_create(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return U.create_user(b.get("name", ""), b.get("comment", ""), b.get("key"))


@router.delete("/users/{name}")
def users_delete(name: str, auth=Depends(require_auth)):
    return U.remove_user(name)


@router.get("/users/{name}/dirs")
def users_dirs(name: str, auth=Depends(require_auth)):
    return {"dirs": U.list_dir_access(name)}


@router.post("/users/{name}/dirs")
def users_dirs_add(name: str, body: dict = None, auth=Depends(require_auth)):
    return U.grant_dir(name, (body or {}).get("path", ""))


@router.post("/users/{name}/dirs/remove")
def users_dirs_remove(name: str, body: dict = None, auth=Depends(require_auth)):
    return U.revoke_dir(name, (body or {}).get("path", ""))


# ---------- SSH ----------
@router.get("/ssh/{user}")
def ssh_list(user: str, auth=Depends(require_auth)):
    return {"keys": S.list_keys(user)}


@router.post("/ssh/{user}")
def ssh_add(user: str, body: dict = None, auth=Depends(require_auth)):
    return S.add_key(user, (body or {}).get("key", ""))


@router.delete("/ssh/{user}/{index}")
def ssh_remove(user: str, index: int, auth=Depends(require_auth)):
    return S.remove_key(user, index)


# ---------- 下载统计 ----------
@router.get("/stats/downloads")
def stats_downloads(auth=Depends(require_auth)):
    return DL.downloads()
