"""多应用管理：应用注册、部署配置、版本管理、反代路由集成。

应用注册在 /etc/aups/apps.json；每个应用有唯一名称、目录和部署配置。
部署配置包含：域名、SSL、端口、工作目录、系统用户、CI 用户/SSH 密钥。
版本从文件名解析（支持 APK/JAR/TAR.GZ 等）。
反代路由：通过 rproxy 公共 API 与 caddy/nginx 解耦。
"""

import json
import os
import re

from ... import config
from ...errors import AppError
from ...util import run

_APK_RE = re.compile(r".+?[_-](v?\d+(?:\.\d+)*)\.apk$", re.IGNORECASE)
_VER_RE = re.compile(r"(?:^|[_-])v?(\d+(?:\.\d+)+)", re.IGNORECASE)


def _registry():
    path = config.APPS_FILE
    if os.path.isfile(path):
        try:
            return json.load(open(path))
        except (OSError, ValueError):
            pass
    return {"apps": {}, "total_quota_mb": 0}


def _save_registry(reg):
    os.makedirs(config.CONF_DIR, exist_ok=True)
    tmp = config.APPS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.APPS_FILE)


def _norm_name(name):
    name = (name or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name):
        raise AppError("应用名只能包含字母、数字、._-，且不能以 . 或 - 开头")
    return name.lower()


def _version_key(vstr):
    try:
        return tuple(int(x) for x in vstr.split("."))
    except (ValueError, TypeError):
        return (0,)


def parse_version(filename):
    """从文件名解析版本号。支持 APK 和通用版本格式。"""
    m = _APK_RE.search(filename)
    if m:
        return m.group(1).lstrip("v")
    m = _VER_RE.search(filename)
    if m:
        return m.group(1)
    return None


def _quota_mb(meta):
    try:
        return int(meta.get("quota_mb", 0))
    except (TypeError, ValueError):
        return 0


def _locked(meta):
    locked = meta.get("locked", [])
    return locked if isinstance(locked, list) else []


def _deploy(meta):
    return meta.get("deploy", {})


# -------------------- 应用 CRUD --------------------

def list_apps():
    reg = _registry().get("apps", {})
    return [
        {
            "name": name,
            "dir": meta.get("dir", ""),
            "comment": meta.get("comment", ""),
            "quota_mb": _quota_mb(meta),
            "locked": list(_locked(meta)),
            "deploy": _deploy(meta),
        }
        for name, meta in sorted(reg.items())
    ]


def get_app(name):
    reg = _registry().get("apps", {})
    meta = reg.get(name)
    if not meta:
        raise AppError(f"应用未注册：{name}")
    return {"name": name, "dir": meta.get("dir", ""), "comment": meta.get("comment", ""),
            "quota_mb": _quota_mb(meta), "locked": list(_locked(meta)),
            "deploy": _deploy(meta)}


def app_exists(name):
    return name in _registry().get("apps", {})


def add_app(name, path=None, comment=""):
    name = _norm_name(name)
    if app_exists(name):
        raise AppError(f"应用已注册：{name}")
    if path:
        real = os.path.realpath(path)
        os.makedirs(real, exist_ok=True)
    else:
        real = os.path.join(config.BASE_DIR, name)
        os.makedirs(real, exist_ok=True)
    reg = _registry()
    reg.setdefault("apps", {})[name] = {
        "dir": real, "comment": comment or "",
        "deploy": {"domain": "", "ssl": {"mode": "none"}, "port": 0},
    }
    _save_registry(reg)
    return get_app(name)


def remove_app(name):
    reg = _registry()
    if name not in reg.get("apps", {}):
        raise AppError(f"应用未注册：{name}")
    meta = reg["apps"].pop(name)
    _save_registry(reg)
    return {"name": name, "removed": True, "dir": meta.get("dir", "")}


def app_dir(name):
    return get_app(name)["dir"]


# -------------------- 部署配置 --------------------

def set_deploy(name, **kwargs):
    """设置应用部署配置（domain/ssl/port/workdir/user/ci_user/ssh_key/proxy）。"""
    reg = _registry()
    meta = reg.get("apps", {}).get(name)
    if not meta:
        raise AppError(f"应用未注册：{name}")
    deploy = meta.setdefault("deploy", {})
    for k in ("domain", "port", "workdir", "user", "ci_user", "ssh_key", "comment", "proxy"):
        if k in kwargs and kwargs[k] is not None:
            deploy[k] = kwargs[k]
    if "ssl" in kwargs and isinstance(kwargs["ssl"], dict):
        deploy.setdefault("ssl", {}).update(kwargs["ssl"])
    if "port" in kwargs:
        try:
            deploy["port"] = int(kwargs["port"])
        except (TypeError, ValueError):
            pass
    _save_registry(reg)
    return get_app(name)


def get_deploy(name):
    return get_app(name).get("deploy", "")


def validate_domain(domain, workdir=""):
    """校验域名是否指向本机：在工作目录写入随机文件，通过 HTTP 访问验证。
    无工作目录时只验证域名解析。
    """
    import random
    import string
    import urllib.request
    import urllib.error
    import socket

    if not domain:
        return {"ok": False, "message": "域名不能为空"}

    # 检查域名解析到本机 IP
    try:
        ip = socket.gethostbyname(domain)
    except socket.gaierror:
        return {"ok": False, "message": f"域名 {domain} 无法解析"}

    # 如果没有工作目录，只检查域名解析
    if not workdir:
        return {"ok": True, "message": f"域名 {domain} 解析到 {ip}（未指定工作目录，跳过文件验证）"}

    real_dir = os.path.realpath(workdir)
    if not os.path.isdir(real_dir):
        return {"ok": False, "message": f"工作目录不存在：{real_dir}"}

    # 生成随机测试文件
    rand_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    test_file = os.path.join(real_dir, f".aups_test_{rand_name}.txt")
    test_content = f"aups-domain-verify-{rand_name}"

    try:
        with open(test_file, "w") as f:
            f.write(test_content)

        # 尝试通过域名访问
        for scheme in ("http", "https"):
            url = f"{scheme}://{domain}/.aups_test_{rand_name}.txt"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AUPS/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    body = resp.read().decode()
                    if test_content in body:
                        return {"ok": True, "message": f"域名 {domain} 已验证指向本机（{ip}）"}
            except (urllib.error.URLError, OSError):
                continue

        return {"ok": False, "message": f"域名 {domain} 解析到 {ip}，但 HTTP 访问未通过（请检查反代配置）"}
    finally:
        try:
            os.remove(test_file)
        except OSError:
            pass


# -------------------- 版本管理 --------------------

def list_versions(name):
    base = os.path.realpath(app_dir(name))
    versions = []
    if os.path.isdir(base):
        for root, _dirs, files in os.walk(base):
            for fn in sorted(files):
                lower = fn.lower()
                if not any(lower.endswith(ext) for ext in (".apk", ".jar", ".tar.gz", ".zip")):
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
                cnt += sum(1 for fn in files if fn.lower().endswith((".apk", ".jar", ".zip")))
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
    reg = _registry()
    try:
        return int(reg.get("total_quota_mb", 0))
    except (TypeError, ValueError):
        return 0


def set_total_quota(quota_mb):
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
    if not real.startswith(base + os.sep):
        return False
    lower = real.lower()
    if not any(lower.endswith(ext) for ext in (".apk", ".jar", ".tar.gz", ".zip")):
        return False
    if not os.path.isfile(real):
        return False
    os.remove(real)
    return True


def enforce_quota(name=None):
    targets = [name] if name else [a["name"] for a in list_apps()]
    removed = {}
    for app in targets:
        reg, meta = _meta(app)
        quota = _quota_mb(meta)
        if quota <= 0:
            continue
        limit = quota * 1024 * 1024
        locked = set(_locked(meta))
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


# -------------------- 反代路由集成 --------------------

def update_proxy_routes(reload=True):
    """触发当前反代重写下载路由并 reload。"""
    from ... import rproxy
    backend = rproxy.backend_name()
    if not backend:
        raise AppError("未检测到可用的反代后端（请安装 caddy/nginx 等）")
    if not rproxy.has_capability("download_route", backend):
        raise AppError(f"反代 {backend} 不支持 download_route 能力")
    try:
        result = rproxy._call(backend, "apply", reload=reload)
    except Exception as e:
        raise AppError(f"反代路由更新失败：{e}")
    return {"backend": backend, "written": True, "reloaded": reload, **result}


def proxy_preview():
    from ... import rproxy
    backend = rproxy.backend_name()
    if not backend:
        return "(未检测到反代后端)"
    if not rproxy.has_capability("preview", backend):
        return f"(反代 {backend} 不支持 preview)"
    return rproxy._call(backend, "preview").get("apps", "")


def request_domain(name):
    """向反代插件请求为应用设定域名。"""
    app = get_app(name)
    domain = app.get("deploy", {}).get("domain", "")
    if not domain:
        raise AppError(f"应用 {name} 未配置域名")
    from ... import rproxy
    backend = rproxy.backend_name()
    if not backend:
        return {"ok": False, "message": "未检测到反代后端"}
    return {"ok": True, "domain": domain, "backend": backend}


def request_ssl(name):
    """向反代插件请求 SSL 证书配置。"""
    app = get_app(name)
    ssl_cfg = app.get("deploy", {}).get("ssl", {})
    if ssl_cfg.get("mode") == "none":
        return {"ok": False, "message": "SSL 未启用"}
    from ... import rproxy
    backend = rproxy.backend_name()
    if not backend:
        return {"ok": False, "message": "未检测到反代后端"}
    return {"ok": True, "ssl": ssl_cfg, "backend": backend}


def request_port(name):
    app = get_app(name)
    port = app.get("deploy", {}).get("port", 0)
    return {"ok": bool(port), "port": port}


def request_workdir(name):
    app = get_app(name)
    workdir = app.get("deploy", {}).get("workdir", "") or app.get("dir", "")
    return {"ok": bool(workdir), "workdir": workdir}


def request_user(name):
    app = get_app(name)
    user = app.get("deploy", {}).get("user", "")
    if not user:
        return {"ok": False, "message": "未配置系统用户"}
    import shutil as _sh
    if not _sh.which("id"):
        return {"ok": False, "message": "id 命令不可用"}
    r = run(["id", "-u", user], check=False)
    if r.returncode != 0:
        return {"ok": False, "message": f"用户 {user} 不存在"}
    return {"ok": True, "user": user}


def request_ssh_key(name):
    app = get_app(name)
    ci_user = app.get("deploy", {}).get("ci_user", "")
    if not ci_user:
        return {"ok": False, "message": "未配置 CI 用户"}
    import pwd as _pwd
    try:
        home = _pwd.getpwnam(ci_user).pw_dir
    except KeyError:
        return {"ok": False, "message": f"用户 {ci_user} 不存在"}
    key_file = os.path.join(home, ".ssh", "authorized_keys")
    if not os.path.isfile(key_file):
        return {"ok": False, "message": " authorized_keys 不存在"}
    try:
        with open(key_file) as f:
            keys = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    except OSError:
        return {"ok": False, "message": "读取 authorized_keys 失败"}
    return {"ok": True, "ci_user": ci_user, "keys": keys}


def remove():
    cron = "/etc/cron.d/aups-enforce-quota"
    try:
        os.remove(cron)
    except OSError:
        pass
    return {"name": "appupdate", "removed": True}
