"""caddy 插件 Web API 路由（由核心自动挂载，前缀 /api）。

包含 Caddy 反代配置、WAF 模板代理（规则存核心 aups.core.waf）、access 日志、
Caddy 端口设置。WAF 规则模板已提升到核心（安全页「WAF 模板」），此处保留
旧 /api/caddyconf/waf 接口以向后兼容，实际读写核心规则库。
"""

from fastapi import APIRouter, Depends, HTTPException

from ...web.websec import require_auth
from ... import rproxy as RP
from ...core import waf as WAFM
from . import env as ENV
from . import caddyfile as CF

router = APIRouter()


# ---------- Caddy 环境部署（status / install）----------
@router.get("/caddy/status")
def caddy_env_status(auth=Depends(require_auth)):
    return ENV.status()


@router.post("/caddy/install")
def caddy_env_install(auth=Depends(require_auth)):
    return ENV.install()


# ---------- 实例控制（stop / restart / reload）----------
@router.post("/caddy/instance/{action}")
def caddy_instance(action: str, auth=Depends(require_auth)):
    """stop / restart / reload。reload 前检查服务状态，未运行时自动启动。"""
    if action == "reload" and ENV.deploy_method() != "container":
        import subprocess as _sp
        b = ENV.caddy_binary()
        if not b:
            raise HTTPException(
                status_code=400,
                detail="Caddy 未安装（未找到 caddy 二进制），无法执行 reload。"
                       + "请先安装 Caddy（aups plugins market install caddy）。")
        try:
            st = _sp.run(["systemctl", "is-active", "caddy"],
                         capture_output=True, text=True, timeout=5)
            if st.stdout.strip() != "active":
                return ENV.instance("start")
        except Exception:
            return ENV.instance("start")
    return ENV.instance(action)


# ---------- Caddyfile 管理（全文件 / 站点块）----------
@router.get("/caddy/caddyfile")
def caddyfile_get(auth=Depends(require_auth)):
    return CF.read()


@router.post("/caddy/caddyfile")
def caddyfile_save(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return CF.write(b.get("content", ""), reload_=bool(b.get("reload", True)))


@router.get("/caddy/sites")
def caddyfile_sites(auth=Depends(require_auth)):
    return CF.list_sites()


@router.post("/caddy/sites")
def caddyfile_site_add(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return CF.create_site(b.get("host", ""), b.get("mode", "reverse_proxy"),
                          b.get("target", ""), b.get("extra", ""))


@router.put("/caddy/sites/{host}")
def caddyfile_site_update(host: str, body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return CF.update_site(host, b.get("mode"), b.get("target"), b.get("extra"))


@router.delete("/caddy/sites/{host}")
def caddyfile_site_delete(host: str, auth=Depends(require_auth)):
    return CF.delete_site(host)


@router.get("/caddy/presets")
def caddyfile_presets(auth=Depends(require_auth)):
    return CF.presets()


# ---------- 反代状态（供实例控制页使用）----------
@router.get("/caddyconf/status")
def caddyconf_status(auth=Depends(require_auth)):
    return RP.status()


# ---------- WAF ----------
@router.get("/caddyconf/waf")
def waf_get(auth=Depends(require_auth)):
    return WAFM.get_config()


@router.post("/caddyconf/waf")
def waf_set(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    if "enabled" in b:
        WAFM.set_enabled(bool(b["enabled"]))
    return WAFM.get_config()


@router.post("/caddyconf/waf/rules")
def waf_rule_add(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return WAFM.add_rule(b.get("kind", ""), b.get("pattern", ""),
                         b.get("field"), b.get("name", ""))


@router.delete("/caddyconf/waf/rules/{rule_id}")
def waf_rule_remove(rule_id: str, auth=Depends(require_auth)):
    return WAFM.remove_rule(rule_id)


@router.post("/caddyconf/waf/rules/{rule_id}/toggle")
def waf_rule_toggle(rule_id: str, body: dict = None, auth=Depends(require_auth)):
    enabled = bool((body or {}).get("enabled"))
    return WAFM.set_rule_enabled(rule_id, enabled)


@router.post("/caddyconf/waf/ips")
def waf_ips(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    which = b.get("list", "")
    action = b.get("action", "")
    ip = b.get("ip", "")
    if action == "add":
        return WAFM.add_ip(which, ip)
    if action == "remove":
        return WAFM.remove_ip(which, ip)
    raise HTTPException(status_code=400, detail="action 需为 add/remove")


@router.post("/caddyconf/waf/ratelimit")
def waf_ratelimit(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return WAFM.set_rate_limit(bool(b.get("enabled")),
                               b.get("requests"), b.get("window"))


@router.post("/caddyconf/waf/subscribe")
def waf_subscribe(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    action = b.get("action", "")
    url = b.get("url", "")
    if action == "set":
        return WAFM.subscribe_set(url, b.get("name", ""), b.get("interval", 3600))
    if action == "remove":
        return WAFM.subscribe_remove(url)
    if action == "sync":
        return WAFM.subscribe_sync(url or None)
    raise HTTPException(status_code=400, detail="action 需为 set/remove/sync")


@router.post("/caddyconf/waf/subscribe/recommended")
def waf_subscribe_recommended(body: dict = None, auth=Depends(require_auth)):
    return WAFM.subscribe_recommended((body or {}).get("interval", 3600))


# ---------- access 日志 ----------
@router.get("/stats/accesslog")
def stats_accesslog_status(auth=Depends(require_auth)):
    return RP.access_log_status()


@router.post("/stats/accesslog")
def stats_accesslog_enable(auth=Depends(require_auth)):
    return RP.enable_access_log()


# ---------- Caddy 运行日志 ----------
@router.get("/caddy/journal")
def caddy_journal(lines: int = 100, auth=Depends(require_auth)):
    """读取 caddy systemd journal 日志（最近 N 行）。"""
    import subprocess as _sp
    try:
        r = _sp.run(["journalctl", "-u", "caddy", "-n", str(min(lines, 500)),
                      "--no-pager", "--output=short-iso"],
                     capture_output=True, text=True, timeout=10)
        raw = r.stdout.strip()
        if r.returncode != 0 and not raw:
            return {"lines": [], "error": r.stderr.strip() or "无法读取 caddy 日志"}
        log_lines = [ln for ln in raw.splitlines() if ln.strip()]
        return {"lines": log_lines[-lines:], "error": None}
    except _sp.TimeoutExpired:
        return {"lines": [], "error": "读取日志超时"}
    except FileNotFoundError:
        return {"lines": [], "error": "journalctl 不可用"}
