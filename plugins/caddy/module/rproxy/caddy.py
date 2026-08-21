"""Caddy 反代后端实现。

负责把「应用下载路由」与「WAF 规则」两段托管片段注入 Caddyfile 的下载站点块
（以 AUP APPS / AUP WAF 标记定位），并 reload Caddy。

WAF 规则来自核心 :mod:`aups.core.waf` 的中性结构，本模块（Caddy 规则转换器）
渲染为 Caddy matcher + respond 403，并支持原生 rate_limit 指令。

下载路由：数据由 appupdate 提供（公共数据：list_apps/list_versions），
本模块负责渲染成 Caddy 语法并维护站点块（Caddyfile 解析是本反代领域职责，
不依赖 appupdate 内部实现）。与 appupdate 解耦。
"""

import os
import re

from .. import env
from ....core import waf
from .... import ports
from ....errors import AppError
from ....util import has_cmd


def _download_routes():
    """读取 appupdate 的公共数据块；首次缺失时调用其声明的公共 API 生成。"""
    try:
        from ....core import contracts
        data = contracts.read_data("caddy", "appupdate", "download_routes")
        if data is None:
            data = contracts.call("caddy", "appupdate", "download_routes")
        return data or {"apps": []}
    except Exception:
        return {"apps": []}

NAME = "caddy"

_WAF_BEGIN = "# >>> AUPS WAF (managed, do not remove) <<<"
_OLD_WAF_BEGIN = "# >>> AUP WAF (managed, do not remove) <<<"
_WAF_END = "# <<< AUPS WAF >>>"
_OLD_WAF_END = "# <<< AUP WAF >>>"


def status():
    instance_status = env.status()
    bin_path = instance_status.get("binary")
    ver = instance_status.get("version")
    caddyfile = env.caddy_config_file()
    deploy = env.deploy_method()
    return {
        "name": NAME,
        "caddyfile": caddyfile,
        "exists": os.path.isfile(caddyfile),
        "binary": bin_path,
        "version": ver,
        "deploy": deploy,
        "container": env.container_status() if deploy == "container" else None,
        "reload_method": ("container" if deploy == "container"
                          else ("systemctl" if has_cmd("systemctl")
                                else ("caddy" if bin_path else None))),
        "waf_enabled": bool(waf.get_config().get("enabled")),
    }


def reload():
    _reload(warn_only=True)
    return {"reloaded": True}


_PORT_RE = re.compile(r"^\s*(https_port|http_port)\s+(\d+)\s*$", re.MULTILINE)


def ports():
    """读取 Caddyfile 中的 https_port/http_port（原核心 read_caddy_ports）。"""
    out = {"https_port": None, "http_port": None}
    try:
        with open(env.caddy_config_file()) as f:
            text = f.read()
    except OSError:
        return out
    for m in _PORT_RE.finditer(text):
        out[m.group(1)] = int(m.group(2))
    return out


def set_port(port):
    """修改 Caddy https_port 并 reload + 放行防火墙（原核心 set_caddy_port）。"""
    if not (1024 <= port <= 65535) or port == 22:
        raise AppError("端口需在 1024-65535 且不能是 22（SSH）")
    caddyfile = env.caddy_config_file()
    try:
        with open(caddyfile) as f:
            text = f.read()
    except OSError:
        raise AppError(f"Caddyfile 不存在：{caddyfile}")
    if not re.search(r"^\s*https_port\s+\d+\s*$", text, re.MULTILINE):
        raise AppError("Caddyfile 中未找到 https_port，请先配置全局块")
    new = re.sub(r"^\s*https_port\s+\d+\s*$", f"https_port {port}", text, count=1, flags=re.MULTILINE)
    with open(caddyfile, "w") as f:
        f.write(new)
    _reload(warn_only=True)
    try:
        ports.firewall_open(port)
    except AppError:
        pass  # 防火墙提示不阻断
    return {"https_port": port}


def _reload(warn_only=False):
    """reload caddy（原核心 reload_caddy），兼容容器/实机部署。"""
    try:
        env.instance("reload")
    except AppError:
        if warn_only:
            return
        raise


# ---------- access 日志 ----------

_LOG_MARK_BEGIN = "# >>> AUPS LOG (managed, do not remove) <<<"
_LOG_MARK_END = "# <<< AUPS LOG >>>"


def _find_global_block(lines):
    """返回 Caddyfile 顶部全局配置块 (start, end) 行索引；无则 None。"""
    i = 0
    while i < len(lines):
        s = lines[i].strip().lstrip("\ufeff")
        if not s or s.startswith("#"):
            i += 1
            continue
        break
    if i >= len(lines) or not lines[i].strip().lstrip("\ufeff").startswith("{"):
        return None
    depth = 0
    j = i
    while j < len(lines):
        depth += lines[j].count("{") - lines[j].count("}")
        if depth == 0:
            return i, j
        j += 1
    return i, len(lines) - 1


def _log_snippet():
    return "\n".join([
        _LOG_MARK_BEGIN,
        "log {",
        f"    output file {env.CADDY_LOG_FILE}",
        "    format json",
        "    include http.log.access",
        "}",
        _LOG_MARK_END,
    ])


def access_log_status():
    """access 日志配置状态（供 Web 总览展示）。"""
    text = ""
    try:
        text = open(env.caddy_config_file(), encoding="utf-8").read()
    except OSError:
        pass
    return {
        "enabled": _LOG_MARK_BEGIN in text or "http.log.access" in text,
        "log_file": env.access_log_file(),
        "file_exists": os.path.isfile(env.access_log_file()),
    }


def enable_access_log():
    """在 Caddyfile 全局块写入 JSON access log 配置并 reload。"""
    if not os.path.isfile(env.caddy_config_file()):
        raise AppError(f"Caddyfile 不存在：{env.caddy_config_file()}")
    with open(env.caddy_config_file(), encoding="utf-8") as f:
        lines = f.read().splitlines()
    if _LOG_MARK_BEGIN in "\n".join(lines):
        return {"enabled": True, "already": True}
    snippet = [_indent_all(ln, "    ") for ln in _log_snippet().splitlines()]
    g = _find_global_block(lines)
    if g:
        start, end = g
        out = lines[:end] + snippet + lines[end:]
    else:
        out = ["{"] + snippet + ["}"] + lines
    with open(env.caddy_config_file(), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    _reload(warn_only=True)
    return {"enabled": True, "already": False}


# ---------- 片段渲染 ----------

def _indent_all(line, indent):
    if not line.strip():
        return line
    return indent + line


def _rule_matcher(r):
    """把中性规则转成 Caddy matcher 行。"""
    kind, pat = r["kind"], r["pattern"]
    field = r.get("field")
    if kind == "path_regex":
        return f"path_regexp {pat}"
    if kind == "user_agent":
        return f"header_regexp User-Agent {pat}"
    if kind == "header":
        return f"header_regexp {field} {pat}"
    if kind == "method":
        return f"method {pat}"
    if kind == "query":
        return f"query {field or 'q'} {pat}"
    return None


def _waf_snippet():
    """生成 WAF 托管片段（Caddy 语法）。"""
    cfg = waf.render_config()
    out = [_WAF_BEGIN]
    if not cfg["enabled"]:
        out.append("# WAF 已禁用（aups caddyconf waf on 启用）")
        out.append(_WAF_END)
        return "\n".join(out)

    whitelist = cfg["whitelist_ips"]
    blacklist = cfg["blacklist_ips"]
    n = 0

    def _not_wl():
        # 白名单内放行：在 matcher 集合中加一条 not remote_ip
        if whitelist:
            return "    not remote_ip " + " ".join(whitelist)
        return None

    if blacklist:
        n += 1
        out.append(f"@waf_ip_{n} {{")
        out.append(f"    remote_ip {' '.join(blacklist)}")
        wl = _not_wl()
        if wl:
            out.append(wl)
        out.append("}")
        out.append(f"respond @waf_ip_{n} 403")

    for i, r in enumerate(cfg["rules"], 1):
        line = _rule_matcher(r)
        if not line:
            continue
        n += 1
        out.append(f"@waf_rule_{n} {{")
        out.append(f"    {line}")
        wl = _not_wl()
        if wl:
            out.append(wl)
        out.append("}")
        out.append(f"respond @waf_rule_{n} 403")

    rl = cfg["rate_limit"]
    if rl.get("enabled"):
        out.append("rate_limit {")
        out.append("    zone aup_waf {")
        out.append("        key {http.request.remote.ip}")
        out.append(f"        events {int(rl.get('requests', 60))}")
        out.append(f"        window {rl.get('window', '10s')}")
        out.append("    }")
        out.append("}")

    if n == 0 and not (rl or {}).get("enabled"):
        out.append("# WAF 已启用但暂无规则（IP/黑名单/限流均可在此配置）")
    out.append(_WAF_END)
    return "\n".join(out)


# ---------- 注入 ----------

# Caddyfile 中 AUPS 托管标记（下载路由区）
_APPS_MARK_BEGIN = "# >>> AUPS APPS (managed, do not remove) <<<"
_OLD_APPS_BEGIN = "# >>> AUP APPS (managed, do not remove) <<<"
_APPS_MARK_END = "# <<< AUPS APPS >>>"
_OLD_APPS_END = "# <<< AUP APPS >>>"

_IGNORE_TOP = (".", "import", "log", "email", "https_port", "http_port", "acme_dns")


def _site_blocks(text):
    """把 Caddyfile 文本拆成顶层站点块。返回 [{host, start, end, body}]，忽略全局块。

    body 是站点块括号内的原始行（含缩进）。Caddyfile 结构解析属反代领域，内部实现。
    """
    blocks = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if "{" in stripped and not stripped.startswith(("#", "//")):
            host = stripped.split("{")[0].strip()
            skip = (not host) or host.startswith(_IGNORE_TOP)
            if not skip:
                depth = 0
                interior = []
                j = i
                while j < n:
                    depth += lines[j].count("{") - lines[j].count("}")
                    if j > i:
                        interior.append(lines[j])
                    if depth == 0:
                        break
                    j += 1
                blocks.append({
                    "host": host,
                    "body": "\n".join(interior[:-1]),
                    "start": i,
                    "end": j,
                })
                i = j + 1
                continue
        i += 1
    return blocks


def _gen_download_routes():
    """从 appupdate 公共数据（list_apps/list_versions）生成 Caddy 下载路由片段。

    数据来源与 appupdate 解耦：只读其公开函数，路由语法渲染为本反代职责。
    appupdate 未启用或停用时返回空片段。
    """
    data = _download_routes()
    parts = [_APPS_MARK_BEGIN]
    for app in data.get("apps", []):
        host = app["name"]
        vers = app.get("versions", [])
        if not vers:
            continue
        parts.append(f"    # -- {host} --")
        for v in vers:
            url = f"/{host}/{v['version']}"
            dl = f"/{host}/{v['rel']}"
            parts.append(f"    @dl_{host}_{v['version']} path {url} /{host}/v{v['version']}")
            parts.append(f"    redir @dl_{host}_{v['version']} {dl}")
        latest = vers[0]
        parts.append(f"    @dl_latest_{host} path /{host}/latest")
        parts.append(f"    redir @dl_latest_{host} /{host}/{latest['rel']}")
    parts.append(_APPS_MARK_END)
    return "\n".join(parts)


def _replace_section(body, begin, end, snippet, insert_top=False):
    """在站点块 body 内替换或插入指定标记区。begin/end 兼容新旧 (AUP/AUPS) 标记。"""
    lines = body.splitlines()
    if begin == _WAF_BEGIN:
        old_begins, old_ends = (_OLD_WAF_BEGIN,), (_OLD_WAF_END,)
    else:
        old_begins, old_ends = (_OLD_APPS_BEGIN,), (_OLD_APPS_END,)
    begin_idx = indent = None
    for i, ln in enumerate(lines):
        if begin in ln or any(ob in ln for ob in old_begins):
            begin_idx = i
            indent = ln[: len(ln) - len(ln.lstrip())]
            break
    if begin_idx is not None:
        end_idx = next((i for i in range(begin_idx, len(lines))
                        if end in lines[i] or any(oe in lines[i] for oe in old_ends)), None)
        insert_at = begin_idx
        drop_count = (end_idx - begin_idx + 1) if end_idx is not None else (len(lines) - begin_idx)
    else:
        insert_at = 0 if insert_top else len(lines)
        drop_count = 0
        indent = "    "
    new_lines = [_indent_all(ln, indent) for ln in snippet.splitlines()]
    lines[insert_at:insert_at + drop_count] = new_lines
    return "\n".join(lines)


def _extract_section(body, begin, end):
    """取标记区原文（含标记行）。begin/end 兼容新旧 (AUP/AUPS) 标记。"""
    if begin == _WAF_BEGIN:
        old_begins, old_ends = (_OLD_WAF_BEGIN,), (_OLD_WAF_END,)
    else:
        old_begins, old_ends = (_OLD_APPS_BEGIN,), (_OLD_APPS_END,)
    out, on = [], False
    for ln in body.splitlines():
        if begin in ln or any(ob in ln for ob in old_begins):
            on = True
        if on:
            out.append(ln)
        if (end in ln or any(oe in ln for oe in old_ends)) and on:
            break
    return "\n".join(out)


def _site():
    """找到托管站点块（含下载路由或 WAF 标记区）。"""
    try:
        text = open(env.caddy_config_file(), encoding="utf-8").read()
    except OSError:
        raise AppError(f"Caddyfile 不存在：{env.caddy_config_file()}")
    blocks = _site_blocks(text)
    target = None
    for blk in blocks:
        if (_APPS_MARK_BEGIN in blk["body"] or _OLD_APPS_BEGIN in blk["body"]
                or _WAF_BEGIN in blk["body"] or _OLD_WAF_BEGIN in blk["body"]):
            target = blk
            break
    if target is None:
        raise AppError(
            "Caddyfile 中未找到 AUPS 托管标记区。请在下载站点块内加一行：\n"
            f"  {_APPS_MARK_BEGIN}\n"
            "（面板会自动把下载路由与 WAF 规则写入该站点块）")
    return text, target


def show():
    text, target = _site()
    body = target["body"]
    return {
        "caddyfile": env.caddy_config_file(),
        "total_lines": len(text.splitlines()),
        "managed": {
            "apps": _extract_section(body, _APPS_MARK_BEGIN, _APPS_MARK_END),
            "waf": _extract_section(body, _WAF_BEGIN, _WAF_END),
        },
    }


def preview():
    return {
        "apps": _gen_download_routes(),
        "waf": _waf_snippet(),
    }


def apply(reload=True):
    text, target = _site()
    lines = text.splitlines()
    body = target["body"]
    body = _replace_section(body, _APPS_MARK_BEGIN, _APPS_MARK_END,
                            _gen_download_routes())
    # WAF 段置于站点块顶部，确保先于 redir/file_server 生效
    body = _replace_section(body, _WAF_BEGIN, _WAF_END, _waf_snippet(), insert_top=True)
    opener = lines[target["start"]]
    closer = lines[target["end"]]
    out = (lines[: target["start"]]
           + [opener]
           + body.splitlines()
           + [closer]
           + lines[target["end"] + 1:])
    with open(env.caddy_config_file(), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    if reload:
        _reload(warn_only=True)
    return {"backend": NAME, "caddyfile": env.caddy_config_file(),
            "written": True, "reloaded": reload}


def update_app_sites(apps, reload_=True):
    """更新 Caddyfile 中的应用站点块（AUPS APPS SITE 标记区）。"""
    from ..caddyfile import update_app_sites as _update
    return _update(apps, reload_=reload_)
