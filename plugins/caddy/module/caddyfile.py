"""caddy 插件：Caddyfile 管理（全文件读写 + 站点块增删改 + 常用片段预设）。

参考 caddydash（https://github.com/WJQSERVER-STUDIO/caddydash）的站点配置与
全局 Caddyfile 管理：站点块解析/生成、Caddyfile 校验与保存、常用片段预设。
本模块负责 Caddyfile 的文本级管理（解析站点块、定位行区间、重建写入），
与反代渲染（rproxy/caddy.py 的托管片段注入）解耦。
"""

import os
import re
import shutil

from ...errors import AppError
from . import env


def _config_file():
    return env.caddy_config_file()


def read():
    """读取完整 Caddyfile。返回 {path, content, lines}。文件不存在返回空内容。"""
    p = _config_file()
    if not os.path.isfile(p):
        return {"path": p, "content": "", "lines": 0, "missing": True}
    with open(p, encoding="utf-8") as f:
        content = f.read()
    return {"path": p, "content": content, "lines": content.count("\n") + 1, "missing": False}


def _validate(content):
    """校验 Caddyfile 语法。返回 None 表示通过，否则返回错误文本。

    实机方式用 caddy validate（无 caddy 二进制时报错，阻止写入无校验的配置）；
    容器方式在容器内校验（挂载目录 /etc/caddy 可见面板配置目录）。
    """
    d = os.path.dirname(_config_file())
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".validate.Caddyfile")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if env.deploy_method() == "container":
            rt = env.container_runtime()
            if not rt:
                return "未检测到容器运行时（docker/podman），无法校验"
            res = env.run([rt, "exec", env.CONTAINER_NAME, "caddy", "validate",
                           "--config", "/etc/caddy/.validate.Caddyfile",
                           "--adapter", "caddyfile"])
        else:
            b = env.caddy_binary()
            if not b:
                return None  # 无 caddy 可校验，跳过（安装后由 apply/reload 再校验）
            res = env.run([b, "validate", "--config", tmp, "--adapter", "caddyfile"])
        if res.returncode != 0:
            return (res.stderr or res.stdout or "Caddyfile 校验失败").strip()
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def write(content, reload_=True):
    """保存完整 Caddyfile：校验 → 备份 → 写入 → reload（reload 失败不阻断保存）。"""
    content = (content or "").replace("\r\n", "\n")
    err = _validate(content)
    if err:
        raise AppError(f"Caddyfile 校验失败：\n{err}")
    p = _config_file()
    if os.path.isfile(p):
        shutil.copy2(p, p + ".bak")
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    reloaded, reload_error = True, None
    if reload_:
        try:
            env.instance("reload")
        except AppError as e:
            reloaded, reload_error = False, str(e)
    return {"path": p, "lines": content.count("\n") + 1,
            "reloaded": reloaded, "reload_error": reload_error}


# ---------- 站点块 ----------

_IGNORE_TOP = (".", "import", "log", "email", "https_port", "http_port", "acme_dns")


def _site_blocks(text):
    """解析 Caddyfile 顶层站点块。返回 [{host, start, end, body}]（行索引）。"""
    blocks = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if "{" in s and not s.startswith(("#", "//")):
            host = s.split("{")[0].strip()
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
                blocks.append({"host": host, "body": "\n".join(interior[:-1]),
                               "start": i, "end": j})
                i = j + 1
                continue
        i += 1
    return blocks


def _site_info(body):
    """从站点块 body 识别模式与目标。"""
    mode, target = "other", ""
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("reverse_proxy"):
            mode = "reverse_proxy"
            t = s.split(None, 1)
            target = t[1].strip() if len(t) > 1 else ""
        elif s.startswith("file_server"):
            mode = "file_server"
        elif s.startswith("root"):
            t = s.split(None, 1)
            root = t[1].strip() if len(t) > 1 else ""
            # 形如 "root * /var/www"：去掉路径匹配符 *
            if root.startswith("*"):
                root = root[1:].strip()
            target = root
    return mode, target


def list_sites():
    """列出 Caddyfile 中的站点块。返回 {sites, path}。"""
    d = read()
    sites = []
    for blk in _site_blocks(d["content"]):
        mode, target = _site_info(blk["body"])
        sites.append({"host": blk["host"], "mode": mode, "target": target,
                      "body": blk["body"], "start": blk["start"], "end": blk["end"]})
    return {"sites": sites, "path": d["path"]}


def get_site(host):
    host = (host or "").strip()
    for s in list_sites()["sites"]:
        if s["host"] == host:
            return s
    raise AppError(f"站点 {host} 不存在")


def _render_site(host, mode, target, extra=""):
    lines = [f"{host} {{"]
    if mode == "reverse_proxy":
        if not target:
            raise AppError("反向代理需填写目标地址（如 localhost:8080）")
        lines.append(f"    reverse_proxy {target}")
    else:
        if not target:
            raise AppError("文件服务需填写站点根目录（root）")
        lines.append(f"    root * {target}")
        lines.append("    file_server")
    if extra:
        for ln in extra.splitlines():
            ln = ln.strip()
            if ln:
                lines.append("    " + ln)
    lines.append("}")
    return "\n".join(lines)


def create_site(host, mode="reverse_proxy", target="", extra=""):
    """新增站点块（reverse_proxy / file_server 两种模式）。"""
    host = (host or "").strip()
    if not host:
        raise AppError("站点域名不能为空")
    if mode not in ("reverse_proxy", "file_server"):
        raise AppError("模式需为 reverse_proxy / file_server")
    d = read()
    for blk in _site_blocks(d["content"]):
        if blk["host"] == host:
            raise AppError(f"站点 {host} 已存在")
    block = _render_site(host, mode, target, extra)
    new = (d["content"].rstrip("\n") + "\n\n" + block + "\n") if d["content"] else block + "\n"
    write(new)
    return {"host": host, "mode": mode, "target": target}


def update_site(host, mode=None, target=None, extra=None):
    """更新站点块：mode/target/extra 提供则覆盖，否则保留原值。"""
    host = (host or "").strip()
    d = read()
    lines = d["content"].splitlines()
    blk = next((b for b in _site_blocks(d["content"]) if b["host"] == host), None)
    if not blk:
        raise AppError(f"站点 {host} 不存在")
    cur_mode, cur_target = _site_info(blk["body"])
    mode = mode or cur_mode or "reverse_proxy"
    target = target if target is not None else cur_target
    if extra is None:
        # 保留原 body 中非 reverse_proxy/root/file_server 的自定义行
        kept = [ln for ln in blk["body"].splitlines()
                if not any(ln.strip().startswith(x)
                           for x in ("reverse_proxy", "root", "file_server"))]
        extra = "\n".join(kept)
    block = _render_site(host, mode, target, extra)
    lines[blk["start"]:blk["end"] + 1] = block.splitlines()
    write("\n".join(lines))
    return {"host": host, "mode": mode, "target": target}


def delete_site(host):
    host = (host or "").strip()
    d = read()
    lines = d["content"].splitlines()
    blk = next((b for b in _site_blocks(d["content"]) if b["host"] == host), None)
    if not blk:
        raise AppError(f"站点 {host} 不存在")
    del lines[blk["start"]:blk["end"] + 1]
    write("\n".join(lines))
    return {"host": host, "deleted": True}


# ---------- 应用站点块（AUPS APPS 管理） ----------

_APPS_SITE_BEGIN = "# >>> AUPS APPS SITE (managed, do not remove) <<<"
_APPS_SITE_END = "# <<< AUPS APPS SITE >>>"


def _gen_app_site_blocks(apps):
    """根据应用注册表生成站点块列表。apps 为 [{name, domain, port, workdir}]。"""
    blocks = []
    for app in apps:
        domain = (app.get("domain") or "").strip()
        port = int(app.get("port") or 0)
        if not domain or not port:
            continue
        block = f"""{domain} {{
    reverse_proxy 127.0.0.1:{port}
}}"""
        blocks.append(block)
    return "\n\n".join(blocks)


def update_app_sites(apps, reload_=True):
    """更新 Caddyfile 中的应用站点块（AUPS APPS SITE 标记区）。
    apps 为 [{name, domain, port, workdir}] 列表。
    """
    d = read()
    content = d["content"]
    new_sites = _gen_app_site_blocks(apps)

    if not new_sites:
        # 无应用站点：移除标记区
        content = _remove_section(content, _APPS_SITE_BEGIN, _APPS_SITE_END)
    else:
        section = f"{_APPS_SITE_BEGIN}\n{new_sites}\n{_APPS_SITE_END}"
        content = _replace_section(content, _APPS_SITE_BEGIN, _APPS_SITE_END, section)

    write(content, reload_=reload_)
    return {"updated": True, "sites": len([a for a in apps if a.get("domain") and a.get("port")])}


def remove_app_site(domain, reload_=True):
    """移除指定域名的应用站点块。"""
    d = read()
    content = d["content"]
    # 找到并移除包含该域名的站点块
    blocks = _site_blocks(content)
    lines = content.splitlines()
    for blk in blocks:
        if blk["host"] == domain:
            del lines[blk["start"]:blk["end"] + 1]
            content = "\n".join(lines)
            break
    write(content, reload_=reload_)
    return {"removed": True, "domain": domain}


def _remove_section(text, begin, end):
    """移除标记区之间的内容（含标记本身）。"""
    lines = text.splitlines()
    result = []
    inside = False
    for line in lines:
        if begin in line:
            inside = True
            continue
        if end in line:
            inside = False
            continue
        if not inside:
            result.append(line)
    return "\n".join(result)


# ---------- 常用片段预设（参考 caddydash） ----------

PRESETS = [
    {"id": "security-headers", "title": "安全响应头",
     "lines": ["header {",
               "    -Server",
               "    X-Content-Type-Options nosniff",
               "    X-Frame-Options DENY",
               "    Referrer-Policy no-referrer",
               '    X-XSS-Protection "1; mode=block"',
               "}"]},
    {"id": "gzip", "title": "gzip 压缩", "lines": ["encode gzip"]},
    {"id": "block-bots", "title": "拦截常见爬虫",
     "lines": ['@block_bots header_regexp User-Agent "(?i)(bot|crawler|spider)"',
               "respond @block_bots 403"]},
    {"id": "static-cache", "title": "静态资源缓存",
     "lines": ['header Cache-Control "public, max-age=86400"',
               "header Vary Accept-Encoding"]},
]


def presets():
    return {"presets": PRESETS}