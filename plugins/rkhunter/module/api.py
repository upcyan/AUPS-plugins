"""rkhunter 插件 Web API 路由（由核心自动挂载，前缀 /api）。

逻辑委托核心 aups.core.hostsec（rkhunter 安装/卸载/扫描/报告）。
"""

from fastapi import APIRouter, Depends, HTTPException

from ...web.websec import require_auth
from . import scanner as SC

router = APIRouter()


@router.get("/rkhunter/status")
def rkhunter_status(auth=Depends(require_auth)):
    return SC.status()


@router.post("/rkhunter/install")
def rkhunter_install(auth=Depends(require_auth)):
    return SC.install()


@router.post("/rkhunter/reinstall")
def rkhunter_reinstall(auth=Depends(require_auth)):
    return SC.reinstall()


@router.post("/rkhunter/uninstall")
def rkhunter_uninstall(auth=Depends(require_auth)):
    return SC.uninstall()


@router.post("/rkhunter/scan")
def rkhunter_scan(body: dict = None, auth=Depends(require_auth)):
    return SC.scan((body or {}).get("paths"))


@router.get("/rkhunter/reports")
def rkhunter_reports(auth=Depends(require_auth)):
    return {"reports": SC.reports()}


@router.get("/rkhunter/report/{rid}")
def rkhunter_report(rid: str, auth=Depends(require_auth)):
    return SC.report(rid)