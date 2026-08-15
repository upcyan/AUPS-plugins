"""lmd 插件 Web API 路由（由核心自动挂载，前缀 /api）。

安装/卸载/扫描由本插件 scanner 实现；报告/隔离区数据层委托核心 aups.core.hostsec。
"""

from fastapi import APIRouter, Depends, HTTPException

from ...web.websec import require_auth
from . import scanner as SC

router = APIRouter()


@router.get("/lmd/status")
def lmd_status(auth=Depends(require_auth)):
    return SC.status()


@router.post("/lmd/install")
def lmd_install(auth=Depends(require_auth)):
    return SC.install()


@router.post("/lmd/reinstall")
def lmd_reinstall(auth=Depends(require_auth)):
    return SC.reinstall()


@router.post("/lmd/uninstall")
def lmd_uninstall(auth=Depends(require_auth)):
    return SC.uninstall()


@router.post("/lmd/scan")
def lmd_scan(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return SC.scan(b.get("paths"), b.get("quarantine", True))


@router.get("/lmd/reports")
def lmd_reports(auth=Depends(require_auth)):
    return {"reports": SC.reports()}


@router.get("/lmd/report/{rid}")
def lmd_report(rid: str, auth=Depends(require_auth)):
    return SC.report(rid)


@router.get("/lmd/quarantine")
def lmd_quarantine(auth=Depends(require_auth)):
    return {"items": SC.quarantine_list()}


@router.post("/lmd/quarantine/restore")
def lmd_quarantine_restore(body: dict = None, auth=Depends(require_auth)):
    return SC.quarantine_restore((body or {}).get("name", ""))