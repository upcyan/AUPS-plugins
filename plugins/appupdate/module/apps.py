"""多应用管理：应用注册中心、版本解析、Caddy 下载路由自动生成。

应用注册在 /etc/aups/apps.json；每个应用有唯一的名称和目录。
版本从 APK 文件名解析（如 dateforshift-0.1.0007.apk → 0.1.0007）。
Caddy 下载路由：每个应用注册后，可自动把其版本的下载重定向规则写入 Caddyfile。
"""

import json
import os
import re

from ... import config
from ...errors import AppError
from ...util import run

_APK_RE = re.compile(r".+?[_-](v?\d+(?:\.\d+)*)\.apk$", re.IGNORECASE)


def _registry():
    path = config.APPS_FILE
    if os.path.isfile(path):
        try:
            return json.load(open(path))
        except (OSError, ValueError):
            pass
    return {"apps": {}}


def _save_registry(reg):
    os.makedirs(config.CONF_DIR, exist_ok=True)
    with open(config.APPS_FILE, "w") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def _norm_name(name):
    name = (name or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name):
        raise AppError("应用名只能包含字母、数字、._-，且不能以 . 或 - 开头")
    return name.lower()


def parse_version(filename):
    """从 APK 文件名解析版本号。返回 version 字符串，或 None。"""
    m = _APK_RE.search(filename)
    if not m:
        return None
    return m.group(1).lstrip("v")


def _version_key(vstr):
    return tuple(int(x) for x in vstr.split("."))


def _quota_mb(meta):
    try:
        return int(meta.get("quota_mb", 0))
    except (TypeError, ValueError):
        return 0


def _locked(meta):
    locked = meta.get("locked", [])
    return locked if isinstance(locked, list) else []


def list_apps():
    reg = _registry().get("apps", {})
    return [
        {
            "name": name,
            "dir": meta.get("dir", ""),
            "comment": meta.get("comment", ""),
            "quota_mb": _quota_mb(meta),
            "locked": list(_locked(meta)),
        }
        for name, meta in sorted(reg.items())
    ]


def get_app(name):
    reg = _registry().get("apps", {})
    meta = reg.get(name)
    if not meta:
        raise AppError(f"应用未注册：{name}")
    return {"name": name, "dir": meta.get("dir", ""), "comment": meta.get("comment", ""),
            "quota_mb": _quota_mb(meta), "locked": list(_locked(meta))}


def app_exists(name):
    return name in _registry().get("apps", {})


def add_app(name, path=None, comment=""):
    name = _norm_name(name)
    if app_exists(name):
        raise AppError(f"应用已注册：{name}")
    if path:
        real = os.path.realpath(path)
        if not os.path.isdir(real):
            os.makedirs(real, exist_ok=True)
    else:
        real = os.path.join(config.BASE_DIR, name)
        os.makedirs(real, exist_ok=True)
    reg = _registry()
    reg["apps"][name] = {"dir": real, "comment": comment or ""}
    _save_registry(reg)
    return {"name": name, "dir": real, "comment": comment or ""}


def remove_app(name):
    reg = _registry()
    if name not in reg.get("apps", {}):
        raise AppError(f"应用未注册：{name}")
    meta = reg["apps"][name]
    reg["apps"].pop(name, None)
    _save_registry(reg)
    return {"name": name, "removed": True, "dir": meta.get("dir", "")}


def app_dir(name):
    return get_app(name)["dir"]


def list_versions(name):
    """列出应用目录下所有 APK 的版本，按版本号降序。"""
    base = os.path.realpath(app_dir(name))
    versions = []
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            for fn in sorted(files):
                if not fn.lower().endswith(".apk"):
                    continue
                vstr = parse_version(fn)
                if not vstr:
                    continue
                path = os.path.join(root, fn)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                versions.append({
                    "version": vstr,
                    "file": path,
                    "rel": os.path.relpath(path, base).replace(os.sep, "/"),
                    "size_bytes": size,
                })
    return sorted(versions, key=lambda v: _version_key(v["version"]), reverse=True)


def latest_version(name):
    vs = list_versions(name)
    if not vs:
        return None
    v = vs[0]
    return {"version": v["version"], "rel": v["rel"], "size_bytes": v["size_bytes"]}


def discover():
    """扫描站点目录，找出含 APK 但尚未注册的目录作为候选应用。"""
    base = os.path.realpath(config.BASE_DIR)
    registered = set()
    for a in list_apps():
        try:
            registered.add(os.path.realpath(a["dir"]))
        except (TypeError, ValueError):
            pass
    candidates = []
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            p = os.path.join(base, entry)
            if not os.path.isdir(p):
                continue
            real = os.path.realpath(p)
            if real in registered:
                continue
            cnt = 0
            for root, _dirs, files in os.walk(real):
                cnt += sum(1 for fn in files if fn.lower().endswith(".apk"))
            if cnt:
                candidates.append({"name": entry, "dir": real, "apk_count": cnt})
    return {"base": base, "candidates": candidates}


# -------------------- 配额与版本锁定 --------------------

def _meta(name):
    reg = _registry()
    meta = reg.get("apps", {}).get(name)
    if not meta:
        raise AppError(f"应用未注册：{name}")
    return reg, meta


def set_quota(name, quota_mb):
    """设置应用容量配额（MB）。0 表示不限。不能超过总配额。"""
    reg, meta = _meta(name)
    quota_mb = int(quota_mb)
    if quota_mb < 0 or quota_mb > 2 ** 31 - 1:
        raise AppError("配额需在 0-2147483647 之间（MB）")
    total = int(reg.get("total_quota_mb", 0))
    if total and quota_mb > total:
        raise AppError(f"应用配额({quota_mb}MB)不能超过总配额({total}MB)")
    meta["quota_mb"] = quota_mb
    _save_registry(reg)
    return get_app(name)


def get_total_quota():
    """全局总容量配额（MB，0=不限）。"""
    reg = _registry()
    try:
        return int(reg.get("total_quota_mb", 0))
    except (TypeError, ValueError):
        return 0


def set_total_quota(quota_mb):
    """设置全局总容量配额（MB，0=不限）。不能小于任一应用配额。"""
    reg = _registry()
    quota_mb = int(quota_mb)
    if quota_mb < 0 or quota_mb > 2 ** 31 - 1:
        raise AppError("配额需在 0-2147483647 之间（MB）")
    if quota_mb:
        max_app = max((_quota_mb(m) for m in reg.get("apps", {}).values()), default=0)
        if quota_mb < max_app:
            raise AppError(f"总配额({quota_mb}MB)不能小于应用配额最大值({max_app}MB)")
    reg["total_quota_mb"] = quota_mb
    _save_registry(reg)
    return {"total_quota_mb": quota_mb}


def lock_version(name, version):
    """锁定某版本，容量清理时不会被删除。"""
    reg, meta = _meta(name)
    locked = meta.setdefault("locked", [])
    if version not in locked:
        locked.append(version)
    _save_registry(reg)
    return {"name": name, "version": version, "locked": list(locked)}


def unlock_version(name, version):
    reg, meta = _meta(name)
    locked = meta.setdefault("locked", [])
    if version in locked:
        locked.remove(version)
    _save_registry(reg)
    return {"name": name, "version": version, "locked": list(locked)}


def _delete_apk_safe(path):
    base = os.path.realpath(config.BASE_DIR)
    real = os.path.realpath(path)
    if not real.endswith(".apk") or not real.startswith(base + os.sep):
        return False
    if not os.path.isfile(real):
        return False
    os.remove(real)
    return True


def enforce_quota(name=None):
    """按配额清理：应用总大小超过 quota_mb 时，删除最老的未锁定版本，直到达标。

    name 为空时对所有已注册应用执行。返回 {app: [删除文件]}。
    """
    targets = [name] if name else [a["name"] for a in list_apps()]
    removed = {}
    for app in targets:
        reg, meta = _meta(app)
        quota = _quota_mb(meta)
        if quota <= 0:
            continue
        limit = quota * 1024 * 1024
        locked = set(_locked(meta))
        # 降序（最新在前）
        vers = list_versions(app)
        total = sum(v["size_bytes"] for v in vers)
        keep = []
        for v in vers:
            if total <= limit:
                keep.append(v)
                continue
            if v["version"] in locked:
                keep.append(v)
                continue
            if _delete_apk_safe(v["file"]):
                total -= v["size_bytes"]
        removed[app] = [v["file"] for v in vers if v not in keep]
    if name is None:
        _enforce_total_quota(removed)
    return removed


def _enforce_total_quota(removed):
    """总配额超出时，全局删除最老的未锁定版本直到达标。"""
    total_q = get_total_quota()
    if total_q <= 0:
        return
    limit = total_q * 1024 * 1024
    reg = _registry()
    rows = []
    for app in reg.get("apps", {}):
        meta = reg["apps"][app]
        locked = set(_locked(meta))
        for v in list_versions(app):
            rows.append({"app": app, "file": v["file"], "version": v["version"],
                         "size": v["size_bytes"], "locked": v["version"] in locked})
    rows.sort(key=lambda x: _version_key(x["version"]))
    total = sum(r["size"] for r in rows)
    for r in rows:
        if total <= limit:
            break
        if r["locked"]:
            continue
        if _delete_apk_safe(r["file"]):
            total -= r["size"]
            removed.setdefault(r["app"], []).append(r["file"])


# -------------------- Caddy 路由生成 --------------------

_CADDY_MARK_BEGIN = "# >>> AUPS APPS (managed, do not remove) <<<"
_OLD_MARK_BEGIN = "# >>> AUP APPS (managed, do not remove) <<<"
_CADDY_MARK_END = "# <<< AUPS APPS >>>"
_OLD_MARK_END = "# <<< AUP APPS >>>"

_IGNORE_TOP = (".", "import", "log", "email", "https_port", "http_port", "acme_dns")


def _site_blocks(text):
    """把 Caddyfile 文本拆成顶层站点块。返回 [{host, start, end, body}]，忽略全局块。

    body 是站点块括号内的原始行（含缩进）。
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
                    "body": "\n".join(interior[:-1]),  # 去尾部闭合行 }
                    "start": i,
                    "end": j,
                })
                i = j + 1
                continue
        i += 1
    return blocks


def _gen_routes():
    """根据已注册应用生成 Caddy 路由片段（marker 包裹）。"""
    parts = [_CADDY_MARK_BEGIN]
    apps = list_apps()
    for app in apps:
        host = app["name"]
        vers = list_versions(host)
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
    parts.append(_CADDY_MARK_END)
    return "\n".join(parts)


def _replace_marker(body, routes):
    """在站点块 body 中替换或插入 marker 区。"""
    lines = body.splitlines()
    begin_idx = indent = None
    for i, ln in enumerate(lines):
        if _CADDY_MARK_BEGIN in ln or _OLD_MARK_BEGIN in ln:
            begin_idx = i
            indent = ln[: len(ln) - len(ln.lstrip())]
            break
    if begin_idx is not None:
        end_idx = next((i for i in range(begin_idx, len(lines))
                        if (_CADDY_MARK_END in lines[i] or _OLD_MARK_END in lines[i])), None)
        insert_at = begin_idx
        drop_count = (end_idx - begin_idx + 1) if end_idx is not None else (len(lines) - begin_idx)
    else:
        insert_at = len(lines)
        drop_count = 0
        indent = "    "
    new_lines = [_add_indent(ln, indent) for ln in routes.splitlines()]
    lines[insert_at:insert_at + drop_count] = new_lines
    return "\n".join(lines)


def _add_indent(line, indent):
    if not line:
        return line
    if line.lstrip().startswith(("#", "@", "redir")):
        return indent + line.strip()
    return line


def update_caddy_routes(reload=True):
    """把应用路由片断写回 Caddyfile（marker 定位替换），可选 reload。返回 {caddyfile, written}。"""
    from ..caddy import env as caddy_env
    from ... import rproxy
    caddyfile = caddy_env.caddy_config_file()
    routes = _gen_routes()
    try:
        with open(caddyfile, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        raise AppError(f"Caddyfile 不存在：{caddyfile}")

    blocks = _site_blocks("\n".join(lines))
    target = None
    for block in blocks:
        if _CADDY_MARK_BEGIN in block["body"] or _OLD_MARK_BEGIN in block["body"]:
            target = block
            break
    if target is None:
        raise AppError(
            "Caddyfile 中未找到 AUPS APPS 标记区。请在下载站点块内加入一行：\n"
            f"  {_CADDY_MARK_BEGIN}\n"
            "（会自动在该行之后写入路由，站点块结尾无需手动加结束标记）")

    old_body = target["body"]
    new_body = _replace_marker(old_body, routes)
    # start 为站点块起始行（含 host {），end 为闭合行（}），仅替换二者之间的内部行
    opener = lines[target["start"]]
    closer = lines[target["end"]]
    out = (lines[: target["start"]]
           + [opener]
           + new_body.splitlines()
           + [closer]
           + lines[target["end"] + 1:])
    with open(caddyfile, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    if reload:
        rproxy.reload()
    return {"caddyfile": caddyfile, "written": True}


def _caddy_preview():
    """只打印将写入 Caddyfile 的路由片段，不做修改。"""
    return _gen_routes()