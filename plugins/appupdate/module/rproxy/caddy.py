"""Caddy 反代后端实现。

负责把「应用下载路由」与「WAF 规则」两段托管片段注入 Caddyfile 的下载站点块
（以 AUP APPS / AUP WAF 标记定位），并 reload Caddy。

WAF 规则通过 :mod:`aups.waf` 的中性结构渲染为 Caddy matcher + respond 403，
并支持原生 rate_limit 指令（需 Caddy 2.9+ 内置该指令）。
"""

import os

from .... import apps
from .... import config
from .... import ports
from .... import waf
from ....errors import AppError
from ....util import has_cmd, run

NAME = "caddy"

_WAF_BEGIN = "# >>> AUPS WAF (managed, do not remove) <<<"
_OLD_WAF_BEGIN = "# >>> AUP WAF (managed, do not remove) <<<"
_WAF_END = "# <<< AUPS WAF >>>"
_OLD_WAF_END = "# <<< AUP WAF >>>"


def status():
    ver = None
    if has_cmd("caddy"):
        r = run(["caddy", "version"])
        if r.returncode == 0 and r.stdout.strip():
            ver = r.stdout.strip().split()[0]
    return {
        "name": NAME,
        "caddyfile": config.CADDYFILE,
        "exists": os.path.isfile(config.CADDYFILE),
        "version": ver,
        "reload_method": ("systemctl" if has_cmd("systemctl")
                          else ("caddy" if has_cmd("caddy") else None)),
        "waf_enabled": bool(waf.get_config().get("enabled")),
    }


def reload():
    ports.reload_caddy(warn_only=True)
    return {"reloaded": True}


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
        f"    output file {config.CADDY_LOG_FILE}",
        "    format json",
        "    include http.log.access",
        "}",
        _LOG_MARK_END,
    ])


def access_log_status():
    """access 日志配置状态（供 Web 总览展示）。"""
    text = ""
    try:
        text = open(config.CADDYFILE, encoding="utf-8").read()
    except OSError:
        pass
    return {
        "enabled": _LOG_MARK_BEGIN in text or "http.log.access" in text,
        "log_file": config.CADDY_LOG_FILE,
        "file_exists": os.path.isfile(config.CADDY_LOG_FILE),
    }


def enable_access_log():
    """在 Caddyfile 全局块写入 JSON access log 配置并 reload。"""
    if not os.path.isfile(config.CADDYFILE):
        raise AppError(f"Caddyfile 不存在：{config.CADDYFILE}")
    with open(config.CADDYFILE, encoding="utf-8") as f:
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
    with open(config.CADDYFILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    ports.reload_caddy(warn_only=True)
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

def _replace_section(body, begin, end, snippet, insert_top=False):
    """在站点块 body 内替换或插入指定标记区。begin/end 兼容新旧 (AUP/AUPS) 标记。"""
    lines = body.splitlines()
    old_begins = (_OLD_WAF_BEGIN,) if begin == _WAF_BEGIN else (_OLD_MARK_BEGIN,)
    old_ends = (_OLD_WAF_END,) if end == _WAF_END else (_OLD_MARK_END,)
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
    old_begins = (_OLD_WAF_BEGIN,) if begin == _WAF_BEGIN else (_OLD_MARK_BEGIN,)
    old_ends = (_OLD_WAF_END,) if end == _WAF_END else (_OLD_MARK_END,)
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
    """找到托管站点块。"""
    try:
        text = open(config.CADDYFILE, encoding="utf-8").read()
    except OSError:
        raise AppError(f"Caddyfile 不存在：{config.CADDYFILE}")
    blocks = apps._site_blocks(text)
    target = None
    for blk in blocks:
        if (apps._CADDY_MARK_BEGIN in blk["body"] or apps._OLD_MARK_BEGIN in blk["body"]
                or _WAF_BEGIN in blk["body"] or _OLD_WAF_BEGIN in blk["body"]):
            target = blk
            break
    if target is None:
        raise AppError(
            "Caddyfile 中未找到 AUPS 托管标记区。请在下载站点块内加一行：\n"
            f"  {apps._CADDY_MARK_BEGIN}\n"
            "（aups 会自动把下载路由与 WAF 规则写入该站点块）")
    return text, target


def show():
    text, target = _site()
    body = target["body"]
    return {
        "caddyfile": config.CADDYFILE,
        "total_lines": len(text.splitlines()),
        "managed": {
            "apps": _extract_section(body, apps._CADDY_MARK_BEGIN, apps._CADDY_MARK_END),
            "waf": _extract_section(body, _WAF_BEGIN, _WAF_END),
        },
    }


def preview():
    return {
        "apps": apps._gen_routes(),
        "waf": _waf_snippet(),
    }


def apply(reload=True):
    text, target = _site()
    lines = text.splitlines()
    body = target["body"]
    body = _replace_section(body, apps._CADDY_MARK_BEGIN, apps._CADDY_MARK_END,
                            apps._gen_routes())
    # WAF 段置于站点块顶部，确保先于 redir/file_server 生效
    body = _replace_section(body, _WAF_BEGIN, _WAF_END, _waf_snippet(), insert_top=True)
    opener = lines[target["start"]]
    closer = lines[target["end"]]
    out = (lines[: target["start"]]
           + [opener]
           + body.splitlines()
           + [closer]
           + lines[target["end"] + 1:])
    with open(config.CADDYFILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    if reload:
        ports.reload_caddy(warn_only=True)
    return {"backend": NAME, "caddyfile": config.CADDYFILE,
            "written": True, "reloaded": reload}
