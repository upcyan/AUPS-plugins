"""yara 插件 Web API 路由（由核心自动挂载，前缀 /api）。

逻辑统一委托核心 aups.core.yara（规则数据由核心持有），
供核心主机安全扫描 / 实时防护与 cyansecengine 调用。
"""

from fastapi import APIRouter, Depends, HTTPException

from ...core import yara as Y
from ...web.websec import require_auth

router = APIRouter()


@router.get("/yara/status")
def yara_status(auth=Depends(require_auth)):
    return Y.status()


@router.post("/yara/install")
def yara_install(auth=Depends(require_auth)):
    return Y.install()


@router.post("/yara/scan")
def yara_scan(body: dict = None, auth=Depends(require_auth)):
    return Y.scan((body or {}).get("paths"))


@router.get("/yara/reports")
def yara_reports(auth=Depends(require_auth)):
    return {"reports": Y.reports()}


@router.get("/yara/reports/{rid}")
def yara_report(rid: str, auth=Depends(require_auth)):
    return Y.report(rid)


@router.get("/yara/subscribe")
def yara_subscribe(auth=Depends(require_auth)):
    return {"subscriptions": Y.list_subs()}


@router.post("/yara/subscribe")
def yara_subscribe_add(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    action = b.get("action", "")
    if action == "add":
        return Y.add_sub(b.get("url", ""), b.get("name"),
                         b.get("interval_sec", 86400))
    if action == "remove":
        return Y.remove_sub(b.get("url", ""))
    raise HTTPException(status_code=400, detail="action 需为 add/remove")


@router.post("/yara/subscribe/sync")
def yara_subscribe_sync(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return Y.sync(b.get("url"), due_only=bool(b.get("due_only", False)))
