"""remotedebug 插件 Web API（由核心自动挂载，前缀 /api）。

两类调用面：
- 管理面（建会话/查会话/吊销/审计/命令目录）：走面板会话鉴权，须管理员；
- 令牌面（执行只读命令）：不占用面板会话，凭限时随机令牌 + 只读白名单 +
  根目录限制 + 输出脱敏。令牌面同样要求面板以 root 运行。
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from ...web.websec import require_auth
from ...errors import AppError
from . import runner as RUN
from . import store as ST

router = APIRouter()

# 默认允许访问的目录：全部与面板自身相关，不含用户数据目录。
# 可用 AUP_REMOTEDEBUG_ROOTS 覆盖（冒号或逗号分隔），便于非标准安装路径。
DEFAULT_ROOTS = ("/opt/aups", "/etc/aups", "/var/log/caddy", "/var/lib/caddy")


def _default_roots():
    """默认允许目录：环境变量优先，其次 DEFAULT_ROOTS 中真实存在的项。

    不返回不存在的路径——否则「默认配置缺失」会变成执行期难以理解的路径报错；
    这里宁可返回空列表，由调用方给出明确提示。
    """
    import os
    override = os.environ.get("AUP_REMOTEDEBUG_ROOTS", "").strip()
    if override:
        return [r for r in (p.strip() for p in override.replace(",", ":").split(":"))
                if r]
    roots = [r for r in (*DEFAULT_ROOTS,
                         os.environ.get("AUP_BASE_DIR", "")) if r]
    return [r for r in roots if os.path.isdir(r)]


def _session_roots(session):
    """会话 roots 优先；为空时用默认集合。两者都空则明确报错。"""
    roots = [r for r in (session.get("roots") or []) if r]
    if roots:
        return roots
    roots = _default_roots()
    if not roots:
        raise AppError("未配置可访问目录：请在开放会话时指定 roots，"
                       "或设置环境变量 AUP_REMOTEDEBUG_ROOTS，"
                       "或确认面板目录（/opt/aups 等）存在")
    return roots


# ---------- 管理面（面板会话鉴权） ----------

@router.get("/remotedebug/status")
def rd_status(auth=Depends(require_auth)):
    """框架状态：命令目录、可用性、有效会话数与审计条数。"""
    sessions = ST.list_sessions()
    return {"name": "remotedebug", "mode": "read-only",
            "roots": _default_roots(),
            "catalog": RUN.catalog(),
            "environment": RUN.environment(),
            "sessions": len(sessions),
            "min_ttl": ST.MIN_TTL, "max_ttl": ST.MAX_TTL,
            "default_ttl": ST.DEFAULT_TTL,
            "limits": {"max_steps": RUN.MAX_STEPS, "max_timeout": RUN.MAX_TIMEOUT,
                       "max_output": RUN.MAX_OUTPUT},
            # 远程交互式调试（shell/SSH）暂缓，仅保留框架位
            "interactive": {"enabled": False,
                            "note": "远程连接调试模式暂缓，当前仅提供只读命令执行"}}


@router.post("/remotedebug/sessions")
def rd_create(body: dict = None, auth=Depends(require_auth)):
    """开放限时调试会话：返回一次性明文令牌（服务端只存哈希）。"""
    import os
    b = body or {}
    label = str(b.get("label") or "调试会话")
    # 显式传入的目录必须真实存在；未传则用默认集合（默认值可能因环境缺失，
    # 不能反过来把自己校验掉，否则在精简环境里连会话都开不出来）。
    explicit = [str(r).strip() for r in (b.get("roots") or []) if str(r).strip()]
    bad = [r for r in explicit if not os.path.isdir(r)]
    if bad:
        raise AppError("目录不存在：" + "、".join(bad))
    roots = explicit or _default_roots()
    commands = [str(c).strip() for c in (b.get("commands") or []) if str(c).strip()]
    unknown = [c for c in commands if c not in RUN.CATALOG]
    if unknown:
        raise AppError("命令不在只读目录中：" + "、".join(unknown))
    created = ST.create_session(label=label, ttl_seconds=b.get("ttl_seconds"),
                                roots=roots, commands=commands,
                                note=b.get("note", ""))
    return {"ok": True, **created,
            "usage": "curl -H 'X-Debug-Token: <token>' "
                     "'<面板地址>/api/remotedebug/exec' "
                     "-d '{\"command\":\"ls /opt/aups/config/caddy\"}'"}


@router.get("/remotedebug/sessions")
def rd_sessions(auth=Depends(require_auth)):
    return {"sessions": ST.list_sessions()}


@router.post("/remotedebug/sessions/{sid}/revoke")
def rd_revoke(sid: str, auth=Depends(require_auth)):
    return ST.revoke_session(sid)


@router.post("/remotedebug/revoke-all")
def rd_revoke_all(auth=Depends(require_auth)):
    return ST.revoke_all()


@router.get("/remotedebug/audit")
def rd_audit(limit: int = 200, auth=Depends(require_auth)):
    return {"audit": ST.audit_log(limit)}


@router.post("/remotedebug/exec")
def rd_exec(request: Request, body: dict = None):
    """执行只读命令（令牌面）：不占用面板会话。"""
    token = (request.headers.get("X-Debug-Token")
             or (body or {}).get("token") or "")
    session = ST.verify_token(token)
    if session is None:
        raise HTTPException(status_code=401, detail="调试令牌无效、已过期或已吊销")
    import os
    if getattr(os, "geteuid", lambda: 0)() != 0:
        raise HTTPException(status_code=403, detail="管理面板需以 root 运行")

    b = body or {}
    command = str(b.get("command") or b.get("cmd") or "")
    # 会话级范围限制：会话声明了 commands 时，只开放这些命令
    allowed = session.get("commands") or None
    ip = request.client.host if request.client else ""
    try:
        roots = _session_roots(session)
        result = RUN.execute(command, roots=roots,
                             max_steps=b.get("max_steps", RUN.MAX_STEPS),
                             timeout=b.get("timeout", 10),
                             max_output=b.get("max_output", RUN.MAX_OUTPUT),
                             allowed_bins=allowed)
    except AppError as e:
        ST.record_audit(session, command=command, ok=False, ip=ip, note=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # 兜底：任何意外都记审计并给干净 400，不暴露 500 堆栈
        ST.record_audit(session, command=command, ok=False, ip=ip,
                        note=f"内部错误：{type(e).__name__}")
        raise HTTPException(status_code=400,
                            detail=f"命令执行失败：{type(e).__name__}")
    ST.record_audit(session, command=command, ok=result["ok"],
                    exit_code=result.get("exit_code"),
                    duration_ms=result.get("duration_ms"),
                    output_bytes=result.get("output_bytes"),
                    redactions=result.get("redactions"), ip=ip)
    return {"ok": result["ok"], "session": {"sid": session["sid"],
                                            "label": session.get("label"),
                                            "expires_at": session.get("expires_at")},
            "roots": roots, **{k: v for k, v in result.items()
                               if k not in ("ok",)}}


@router.get("/remotedebug/catalog")
def rd_catalog(auth=Depends(require_auth)):
    return {"catalog": RUN.catalog(), "environment": RUN.environment()}
