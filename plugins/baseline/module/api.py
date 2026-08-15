"""baseline 插件 Web API 路由（由核心自动挂载，前缀 /api）。

检查项实现在本插件 scanner；报告数据层委托核心 aups.core.hostsec。
"""

from fastapi import APIRouter, Depends

from ...web.websec import require_auth
from . import scanner as SC

router = APIRouter()


@router.get("/baseline/status")
def baseline_status(auth=Depends(require_auth)):
    return SC.status()


@router.post("/baseline/check")
def baseline_check(auth=Depends(require_auth)):
    return SC.check()


@router.get("/baseline/reports")
def baseline_reports(auth=Depends(require_auth)):
    return {"reports": SC.reports()}


@router.get("/baseline/report/{rid}")
def baseline_report(rid: str, auth=Depends(require_auth)):
    return SC.report(rid)