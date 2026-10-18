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
    """渲染前实时重取 appupdate 公共数据块（CI 经 SSH 直传文件不经面板，
    落盘数据块可能滞后）；appupdate 停用/缺失时退回已落盘数据块。"""
    from ....core import contracts
    try:
        data = contracts.call("caddy", "appupdate", "download_routes")
        if data is not None:
            return data
    except Exception:
        pass
    try:
        return contracts.read_data("caddy", "appupdate", "download_routes") or {"apps": []}
    except Exception:
        return {"apps": []}

NAME = "caddy"


def list_sites():
    """统一站点管理适配：Caddyfile 解析由 caddyfile 模块负责。"""
    from .. import caddyfile
    return caddyfile.list_sites()


def create_site(host, mode="reverse_proxy", target="", extra="", options=None):
    from .. import caddyfile
    return caddyfile.create_site(host, mode, target, extra, options)


def update_site(host, mode=None, target=None, extra=None, options=None):
    from .. import caddyfile
    return caddyfile.update_site(host, mode, target, extra, options)

def validate():
    from .. import caddyfile
    err=caddyfile._validate(caddyfile.read()["content"])
    if err: raise AppError(err)
    return {"ok":True,"message":"Caddyfile 配置有效"}

def logs(kind="access",limit=200):
    path=env.access_log_file()
    try:
        with open(path,encoding="utf-8",errors="replace") as f: lines=f.readlines()[-max(1,min(int(limit),2000)):]
    except OSError: lines=[]
    return {"kind":kind,"path":path,"lines":[x.rstrip("\n") for x in lines]}


def delete_site(host):
    from .. import caddyfile
    return caddyfile.delete_site(host)

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


def apply_waf(cfg=None):
    """核心 WAF 模板变更时主动重写 Caddyfile 的 WAF 托管段并 reload。

    cfg 与 nginx 后端保持同形签名；渲染时由 _waf_snippet 实时读核心，不入参使用。
    """
    return apply(reload=True)


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
        with open(env.caddy_config_file(), encoding="utf-8") as f:
            text = f.read()
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


def _q(s):
    """Caddyfile 参数加引号：含空格/引号的正则不加引号会被拆成多个参数，
    剩余部分被当作下一个参数解析（真实故障：(?i)(union select|...) 从空格处
    断开，"(?i)(union" 之后的 "select|..." 成了新参数，括号失衡报
    unexpected )）。含引号时改用反引号原样包裹。"""
    s = str(s)
    if '"' not in s:
        return f'"{s}"'
    return f"`{s}`"


def _rule_matcher(r):
    """把中性规则转成 Caddy matcher 行。"""
    kind, pat = r["kind"], r["pattern"]
    field = r.get("field")
    if kind == "path_regex":
        return f"path_regexp {_q(pat)}"
    if kind == "user_agent":
        return f"header_regexp User-Agent {_q(pat)}"
    if kind == "header":
        return f"header_regexp {_q(field)} {_q(pat)}"
    if kind == "method":
        return f"method {pat}"
    if kind == "query":
        return f"query {field or 'q'} {_q(pat)}"
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


def _line_brace_delta(line):
    """一行内有效 { - } 数：跳过引号串、\\{ \\} 转义与 {n,m} 量词语法。

    WAF 正则里的字面量括号（如 \\$\\{、{0,80}）不计入块深度，否则块边界
    解析被带偏，把相邻站点块吞进同一个块。
    """
    delta = 0
    in_str = None
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "\"'":
            in_str = ch
            i += 1
            continue
        if ch == "\\" and i + 1 < n and line[i + 1] in "{}":
            i += 2
            continue
        if ch == "{":
            # 正则量词 {0,80}：{ 紧跟数字且形如 {n[,m]}，视为字面量语法
            m = re.match(r"\{\d+(,\d*)?\}", line[i:])
            if m and (i == 0 or line[i - 1] not in " \t"):
                i += m.end()
                continue
            delta += 1
        elif ch == "}":
            delta -= 1
        i += 1
    return delta


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
                interior = []
                j = i
                depth = 0
                while j < n:
                    # 括号上下文感知：跳过引号串、\\{ \\} 转义与 {n,m} 量词，
                    # 字符级计数会被 WAF 正则里的字面量括号带偏（真实故障：
                    # 相邻站点块被吞并，多出孤立 }，报
                    # "subject does not qualify for certificate: '}'"）
                    depth += _line_brace_delta(lines[j])
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


# 可分发文件扩展名：其直链补 Content-Disposition 强制下载
_DL_EXTS = ("apk", "jar", "zip", "tar.gz")


def _render_routes(data):
    """把下载路由数据渲染成 Caddy 片段（含 AUPS APPS 标记区）。

    路由语法渲染是本反代领域职责，数据由 appupdate 提供（见 _download_routes）。
    """
    parts = [_APPS_MARK_BEGIN]
    seen_apps, seen_vers = set(), set()
    for app in data.get("apps", []):
        host = (app.get("name") or "").strip()
        if not host or host in seen_apps:
            # 数据层重复（注册表/接口重复条目）会让同一 @dl_* matcher 渲染两份，
            # caddy 直接拒绝整份配置，这里按名称去重
            continue
        seen_apps.add(host)
        vers = [v for v in (app.get("versions") or [])
                if v.get("version") and v["version"] not in seen_vers
                and not seen_vers.add(v["version"])]
        latest = app.get("latest") or (vers[0] if vers else None)
        if not latest:
            continue
        parts.append(f"    # -- {host} --")
        for v in vers:
            url = f"/{host}/{v['version']}"
            dl = f"/{host}/{v['rel']}"
            parts.append(f"    @dl_{host}_{v['version']} path {url} /{host}/v{v['version']}")
            parts.append(f"    redir @dl_{host}_{v['version']} {dl}")
        parts.append(f"    @dl_latest_{host} path /{host}/latest")
        parts.append(f"    redir @dl_latest_{host} /{host}/{latest['rel']}")
        # 渠道短链：/app/latest-pr /app/latest-beta /app/latest-canary；
        # 渠道内无文件时跳过（不渲染失效短链）。release 渠道复用 /latest。
        for ch, info in (app.get("latest_by_channel") or {}).items():
            if ch == "release" or not info or not info.get("rel"):
                continue
            parts.append(f"    @dl_latest_{ch}_{host} path /{host}/latest-{ch}")
            parts.append(f"    redir @dl_latest_{ch}_{host} /{host}/{info['rel']}")
        # 直链强制下载：短链 302 后浏览器跟随到此处，凭该响应头弹出下载。
        # 用 path_regexp 而非 path 通配符——Caddy 的 path 匹配中 * 不跨 /，
        # 而真实文件常位于子目录（如 /app/apk/x.apk），path /app/*.apk 匹配不到。
        exts = "|".join(re.escape(e) for e in _DL_EXTS)
        parts.append(f"    @dl_file_{host} path_regexp dl_file_{host} "
                     f"^/{re.escape(host)}/.*\\.({exts})$")
        parts.append(f'    header @dl_file_{host} Content-Disposition "attachment"')
    parts.append(_APPS_MARK_END)
    return "\n".join(parts)


def _gen_download_routes():
    """从 appupdate 公共数据生成 Caddy 下载路由片段（全量，供 preview 用）。

    数据来源与 appupdate 解耦：只读其公开函数，路由语法渲染为本反代职责。
    appupdate 未启用或停用时返回空片段。latest 短链目标优先取数据块中的
    latest 字段（appupdate 按文件日期选定），缺省回退版本号最大的文件。

    latest 与版本短链都是无扩展名路径，若由 file_server 直接托管，Caddy 无法
    按扩展名推断 MIME，响应缺 Content-Type；叠加安全头的
    X-Content-Type-Options: nosniff 后浏览器禁止嗅探，会把 APK 当文本内联渲染
    而不是下载。故此处：

    1. 短链一律 302 到带扩展名的真实文件；
    2. 真实文件（.apk/.jar/.zip/.tar.gz）补 Content-Disposition: attachment
       强制下载。不覆盖 Content-Type，保留 file_server 按扩展名的推断结果，
       以免把 jar/zip 误标为 APK 类型。

    redir 在 Caddy 指令序中先于 file_server，故目录内即使存在同名 latest
    物理文件也会优先重定向。
    """
    return _render_routes(_download_routes())


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


def _site_addresses(host):
    """把站点标签归一化为地址集合（与 caddyfile._site_addresses 同规则）。

    在本模块内保留一份，避免反代渲染依赖 caddyfile 的文本管理实现。
    """
    out = set()
    for value in re.split(r"[\s,]+", host or ""):
        value = re.sub(r"^https?://", "", value.strip().lower()).rstrip("/.")
        if value:
            out.add(value)
    return out


def _managed_sites(text):
    """返回所有含 AUPS 托管标记区的站点块（可能多个：每个应用域名一个）。"""
    return [blk for blk in _site_blocks(text)
            if (_APPS_MARK_BEGIN in blk["body"] or _OLD_APPS_BEGIN in blk["body"]
                or _WAF_BEGIN in blk["body"] or _OLD_WAF_BEGIN in blk["body"])]


def _site():
    """找到首个托管站点块（含下载路由或 WAF 标记区）。保留旧签名供 show() 用。"""
    try:
        with open(env.caddy_config_file(), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        raise AppError(f"Caddyfile 不存在：{env.caddy_config_file()}")
    blocks = _managed_sites(text)
    if not blocks:
        raise AppError(
            "Caddyfile 中未找到 AUPS 托管标记区。请在下载站点块内加一行：\n"
            f"  {_APPS_MARK_BEGIN}\n"
            "（面板会自动把下载路由与 WAF 规则写入该站点块）")
    return text, blocks[0]


def _assign_routes(blocks, data):
    """把应用路由分配到各托管站点块，返回 {块下标: [应用]}。

    规则（保证短链在任何情况下都不丢，否则 App 下载会 404）：

    - 声明了 domain 且与块地址匹配 → 只注入该块，避免把 /otherapp/latest
      写进无关站点；
    - 声明了 domain 但没有任何块匹配 → 兜底注入首个托管块。应用尚未部署站点、
      或站点块同步失败（sync 的站点步报错后 apply 仍会执行）时都会走到这里；
    - 未声明 domain → 注入所有托管块，兼容未绑定域名的旧配置。
    """
    apps = data.get("apps", [])
    if not blocks:
        return {}
    assign = {i: [] for i in range(len(blocks))}
    # 裸域名块与它的 http:// 孪生块是同一逻辑站点：两者 _site_addresses 归一化后
    # 地址相同，若都注入同一份路由，会生成两组同名 matcher，caddy 校验报
    # "matcher is defined more than once"。故同一地址只取其一个代表块写入路由。
    seen = set()
    for app in apps:
        domain = (app.get("domain") or "").strip()
        if not domain:
            # 未声明域名：注入所有逻辑站点（每个地址一次）
            for addr, i in _logical_sites(blocks).items():
                assign[i].append(app)
            continue
        addresses = _site_addresses(domain)
        hit = [i for i, blk in enumerate(blocks)
               if _site_addresses(blk["host"]) & addresses]
        if not hit:
            hit = [0]
        for addr, i in _logical_sites(blocks, hit).items():
            assign[i].append(app)
    return assign


def _logical_sites(blocks, indices=None):
    """把站点块合并为「地址 -> 代表块下标」，裸域名与 http:// 孪生块视为同一个。

    HTTPS 块优先作为代表（裸域名块即代表；仅有 http:// 块时用它），
    使路由注入落在主块上，孪生块由 caddyfile 层按主块重建。
    """
    picked = {}
    for i in (range(len(blocks)) if indices is None else indices):
        host = blocks[i]["host"].strip()
        addrs = _site_addresses(host)
        is_http = host.startswith("http://")
        for addr in addrs:
            cur = picked.get(addr)
            if cur is None:
                picked[addr] = i
                continue
            cur_http = blocks[cur]["host"].strip().startswith("http://")
            # 已有 http 块时，遇到非 http 块则替换为代表
            if cur_http and not is_http:
                picked[addr] = i
    return picked


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
    """向所有 AUPS 托管站点块注入下载路由与 WAF 段。

    多应用多域名时按 _assign_routes 分配路由，避免把
    /otherapp/latest 的重定向写进无关站点；WAF 段每块都要有，故逐块渲染。
    """
    try:
        with open(env.caddy_config_file(), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        raise AppError(f"Caddyfile 不存在：{env.caddy_config_file()}")
    from .. import caddyfile
    data = _download_routes()
    # 不依赖此前已执行 update_app_sites：注入步骤本身按注册域名补齐标记，
    # 包括旧托管块及 begin/end 不完整的配置。无关站点不被自动接管。
    text, adopted = caddyfile.ensure_app_site_markers(text, data.get("apps", []))
    targets = _managed_sites(text)
    if not targets:
        domains = sorted({a.get("domain", "") for a in data.get("apps", []) if a.get("domain")})
        raise AppError("无法自动定位应用下载站点；请核对已注册应用的部署域名和面板配置路径。"
                       f"域名：{', '.join(domains) or '(未配置)'}；"
                       f"配置：{env.caddy_config_file()}")

    waf_snippet = _waf_snippet()
    lines = text.splitlines()
    changed = bool(adopted)
    # 先按稳定顺序算好各块的路由分配，再自下而上写回，避免前面的替换使后续块
    # 的行索引失效。
    assign = _assign_routes(targets, data)
    # 孪生块自身不分配路由，但要复用其主块的片段（matcher 加前缀），
    # 否则 80 端口上的短链没有 redir 规则会 404。
    twin_source = {}
    for addr, i in _logical_sites(targets).items():
        for j, t in enumerate(targets):
            if j != i and _site_addresses(t["host"]) & {addr} \
                    and t["host"].strip().startswith("http://"):
                twin_source[j] = i
    rendered = {}
    for i, t in enumerate(targets):
        apps = assign[i] or assign.get(twin_source.get(i, -1), [])
        rendered[id(t)] = _render_routes({"apps": apps})
    for target in sorted(targets, key=lambda b: b["start"], reverse=True):
        body = "\n".join(lines[target["start"] + 1: target["end"]])
        snippet = rendered[id(target)]
        # 孪生块复制了主块的路由片段，同名 matcher 会与主块冲突，需加前缀
        if target["host"].strip().startswith("http://"):
            snippet = caddyfile._rename_matchers(snippet)
        new_body = _replace_section(body, _APPS_MARK_BEGIN, _APPS_MARK_END, snippet)
        # WAF 段置于站点块顶部，确保先于 redir/file_server 生效
        new_body = _replace_section(new_body, _WAF_BEGIN, _WAF_END, waf_snippet,
                                    insert_top=True)
        if new_body == body:
            continue
        lines[target["start"] + 1: target["end"]] = new_body.splitlines()
        changed = True

    if not changed:
        # 托管段无变化：跳过写盘与 reload，周期同步（cron）可安全高频执行
        return {"backend": NAME, "caddyfile": env.caddy_config_file(),
                "written": False, "changed": False, "reloaded": False,
                "sites": len(targets)}
    out = "\n".join(lines)
    # 复用标准保存流程：校验、备份、重载失败回滚。不再忽略重载异常并谎报成功。
    caddyfile.write(out, reload_=reload)
    return {"backend": NAME, "caddyfile": env.caddy_config_file(),
            "written": True, "changed": True, "reloaded": reload,
            "sites": len(targets), "adopted": adopted}


def update_app_sites(apps, reload_=True):
    """更新 Caddyfile 中的应用站点块（AUPS APPS SITE 标记区）。"""
    from ..caddyfile import update_app_sites as _update
    return _update(apps, reload_=reload_)


def _gen_empty_routes():
    return "\n".join([_APPS_MARK_BEGIN, _APPS_MARK_END])


def clear_routes(reload=True):
    """清空全部托管下载路由（appupdate 迁移到其他反代时调用）。

    只清 APPS 短链区，WAF 段与应用站点块保留；切回 caddy 后执行
    apply() 即可按最新数据重新生成路由。无托管标记区时视为无需清理。

    须覆盖所有托管站点块——多应用多域名时每块各有一份短链，只清首个会留下
    陈旧重定向（迁移后仍把请求导向本后端）。
    """
    try:
        with open(env.caddy_config_file(), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return {"cleared": True, "changed": False, "reloaded": False,
                "note": "Caddyfile 不存在，无需清理"}
    targets = _managed_sites(text)
    if not targets:
        return {"cleared": True, "changed": False, "reloaded": False,
                "note": "Caddyfile 中无托管标记区，无需清理"}
    lines = text.splitlines()
    changed = False
    for target in sorted(targets, key=lambda b: b["start"], reverse=True):
        body = "\n".join(lines[target["start"] + 1: target["end"]])
        new_body = _replace_section(body, _APPS_MARK_BEGIN, _APPS_MARK_END,
                                    _gen_empty_routes())
        if new_body == body:
            continue
        lines[target["start"] + 1: target["end"]] = new_body.splitlines()
        changed = True
    if not changed:
        return {"cleared": True, "changed": False, "reloaded": False}
    with open(env.caddy_config_file(), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    if reload:
        _reload(warn_only=True)
    return {"cleared": True, "changed": True, "reloaded": bool(reload),
            "sites": len(targets)}
