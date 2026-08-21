"""漏洞检测插件 Web API 路由（由核心自动挂载，前缀 /api）。

检测与修复实现在本插件 scanner；报告数据层委托核心 aups.core.hostsec。
"""

from fastapi import APIRouter, Depends

from ...web.websec import require_auth
from . import scanner as SC

router = APIRouter()


@router.get("/vuln/status")
def vuln_status(auth=Depends(require_auth)):
    return SC.status()


@router.post("/vuln/check")
def vuln_check(auth=Depends(require_auth)):
    return SC.check()


@router.post("/vuln/fix")
def vuln_fix(body: dict = None, scope: str = None, pkg: str = None,
             auth=Depends(require_auth)):
    """JSON body 为主，保留 query 参数兼容旧调用方。"""
    b = body or {}
    return SC.fix(scope=b.get("scope") or scope or "security",
                  pkg=b.get("pkg") or pkg)


@router.get("/vuln/reports")
def vuln_reports(auth=Depends(require_auth)):
    return {"reports": SC.reports()}


@router.get("/vuln/report/{rid}")
def vuln_report(rid: str, auth=Depends(require_auth)):
    return SC.report(rid)
