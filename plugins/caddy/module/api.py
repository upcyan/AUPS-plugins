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
from . import sslmode as SSL

router = APIRouter()


# ---------- Caddy 环境部署（status / install）----------
@router.get("/caddy/status")
def caddy_env_status(auth=Depends(require_auth)):
    return ENV.status()


@router.post("/caddy/install")
def caddy_env_install(auth=Depends(require_auth)):
    return ENV.install()


# ---------- 实例控制（stop / restart / reload）----------
@router.post("/caddy/instance/reload")
def caddy_reload(auth=Depends(require_auth)):
    return _do_instance("reload")


@router.post("/caddy/instance/stop")
def caddy_stop(auth=Depends(require_auth)):
    return _do_instance("stop")


@router.post("/caddy/instance/start")
def caddy_start(auth=Depends(require_auth)):
    return _do_instance("start")


@router.post("/caddy/instance/restart")
def caddy_restart(auth=Depends(require_auth)):
    return _do_instance("restart")


def _do_instance(action):
    """统一实例控制逻辑。"""
    if action not in ("stop", "restart", "reload", "start"):
        raise HTTPException(status_code=400, detail=f"不支持的操作: {action}")
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
                raise HTTPException(
                    status_code=400,
                    detail="Caddy 服务未运行（systemctl is-active caddy != active），无法 reload。"
                           + "请先启动 Caddy（aups caddy start）。")
        except HTTPException:
            raise
        except Exception:
            pass
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
    """读取当前 Caddy 实例日志（实机 journal / 容器 logs）。"""
    return ENV.logs(lines)


# ---------- SSL 接入方案 ----------
@router.get("/caddy/ssl/status")
def ssl_status(auth=Depends(require_auth)):
    return SSL.status()


@router.post("/caddy/ssl/flexible")
def ssl_apply_flexible(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    return SSL.apply_flexible(b.get("email", ""))


@router.post("/caddy/ssl/dns01")
def ssl_apply_dns01(body: dict = None, auth=Depends(require_auth)):
    b = body or {}
    email = b.get("email", "")
    token = b.get("api_token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="需要 Cloudflare API Token")
    return SSL.apply_dns01(email, token)


@router.post("/caddy/ssl/disable")
def ssl_disable(auth=Depends(require_auth)):
    return SSL.disable_ssl_mode()


@router.get("/caddy/ssl/caddy-with-cloudflare")
def ssl_download_caddy_with_cloudflare(auth=Depends(require_auth)):
    """下载并返回带 cloudflare DNS provider 的 caddy 二进制路径（供前端引导用户替换）。"""
    bin_path = SSL.download_caddy_with_cloudflare()
    return {"ok": True, "path": bin_path, "message": f"已下载: {bin_path}，请替换面板 runtime 目录下的 caddy 并重启"}
