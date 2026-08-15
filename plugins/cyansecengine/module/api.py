"""cyansecengine 插件 Web API 路由（由核心自动挂载，前缀 /api）。

提供安全加固相关接口：引擎状态/安装、扫描与报告、隔离区、规则订阅。
鉴权用核心 websec.require_auth。
"""

from fastapi import APIRouter, Depends, HTTPException

from ...web.websec import require_auth
from . import scanner as SC
from . import subscribe as SUB

router = APIRouter()


# ---------- 状态 / 安装 ----------

@router.get("/cyansec/status")
def cyansec_status(auth=Depends(require_auth)):
    return SC.status()


@router.post("/cyansec/install")
def cyansec_install(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return SC.install(b.get("tool", ""))


# ---------- 扫描 / 报告 ----------

@router.post("/cyansec/scan")
def cyansec_scan(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return SC.scan(b.get("tool", ""), b.get("paths"), b.get("quarantine", True))


@router.get("/cyansec/reports")
def cyansec_reports(auth=Depends(require_auth)):
    return {"reports": SC.reports()}


@router.get("/cyansec/reports/{rid}")
def cyansec_report(rid: str, auth=Depends(require_auth)):
    return SC.report(rid)


# ---------- 隔离区 ----------

@router.get("/cyansec/quarantine")
def cyansec_quarantine(auth=Depends(require_auth)):
    return {"items": SC.quarantine_list()}


@router.post("/cyansec/quarantine/restore")
def cyansec_quarantine_restore(body: dict = None, auth=Depends(require_auth)):
    return SC.quarantine_restore((body or {}).get("name", ""))


# ---------- 规则订阅 ----------

@router.get("/cyansec/subscribe")
def cyansec_subscribe_list(auth=Depends(require_auth)):
    return {"subscriptions": SUB.list_subs()}


@router.post("/cyansec/subscribe")
def cyansec_subscribe(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    action = b.get("action", "")
    if action == "add":
        return {"subscriptions": SUB.add_sub(b.get("url", ""), b.get("name"), b.get("interval", 86400))}
    if action == "remove":
        return {"removed": SUB.remove_sub(b.get("url", ""))}
    raise HTTPException(status_code=400, detail="action 需为 add/remove")


@router.post("/cyansec/subscribe/sync")
def cyansec_subscribe_sync(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return SUB.sync(b.get("url"), due_only=bool(b.get("due_only", False)))
