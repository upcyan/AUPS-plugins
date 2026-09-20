"""多应用管理：应用注册、部署配置、版本管理、反代路由集成。

应用注册在 /etc/aups/apps.json；每个应用有唯一名称、目录和部署配置。
部署配置包含：域名、SSL、端口、工作目录、系统用户、CI 用户/SSH 密钥。
版本从文件名解析（支持 APK/JAR/TAR.GZ 等）。
反代路由：通过 rproxy 公共 API 与 caddy/nginx 解耦。
"""

import json
import os
import re
import time

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


def _norm_domain(domain):
    return (domain or "").strip().lower().rstrip(".")


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


def public_download_routes():
    """导出下载路由数据块（契约 v1），供反代插件读取和渲染。

    versions 按版本号排序（版本短链用）；latest 按文件日期取最新（latest 短链用，
    CI 经 SSH 直传的文件不经面板，只有这里实时扫描才能保证 latest 跟进新文件）。
    """
    from ...core import contracts
    payload = {
        "apps": [{"name": app["name"], "versions": list_versions(app["name"]),
                  "latest": latest_by_date(app["name"])}
                 for app in list_apps()]
    }
    return contracts.write_data("appupdate", "download_routes", payload)


def latest_by_date(name):
    """按文件修改时间取应用目录下最新的可分发文件（latest 短链目标）。"""
    base = os.path.realpath(app_dir(name))
    best = None  # (mtime, rel)
    if os.path.isdir(base):
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith((".apk", ".jar", ".tar.gz", ".zip")):
                    continue
                path = os.path.join(root, fn)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if best is None or mtime > best[0]:
                    best = (mtime, os.path.relpath(path, base).replace(os.sep, "/"))
    if not best:
        return None
    return {"version": parse_version(best[1]) or "", "rel": best[1], "mtime": int(best[0])}


def sync_proxy_routes(reload=True, include_sites=True):
    """项目/文件变更后自动同步反代（新建项目自动获得短链重定向）。

    三步：刷新下载数据块（CI 直传不经面板，渲染前必须重算）→ 应用站点块
    （域名变化时重建）→ 下载路由短链 + WAF 托管段（反代无变化时自动跳过
    写盘与 reload，周期同步可安全高频执行）。无反代后端时静默返回；各步
    失败记入 errors 不抛出，不阻断调用方主流程。
    """
    result = {"backend": None, "data": False, "sites": None, "routes": None, "errors": []}
    try:
        public_download_routes()
        result["data"] = True
    except Exception as e:
        result["errors"].append(f"刷新下载数据失败：{e}")
    try:
        from ... import rproxy
        backend = rproxy.backend_name()
    except Exception:
        return result
    if not backend:
        return result
    result["backend"] = backend
    if include_sites:
        app_sites = [{"name": a["name"], "domain": (a.get("deploy") or {}).get("domain", ""),
                      "port": (a.get("deploy") or {}).get("port", 0),
                      "workdir": (a.get("deploy") or {}).get("workdir") or a.get("dir", "")}
                     for a in list_apps()]
        try:
            result["sites"] = rproxy.update_app_sites(app_sites, reload=False)
        except Exception as e:
            result["errors"].append(f"同步应用站点块失败：{e}")
    if rproxy.has_capability("download_route", backend):
        try:
            result["routes"] = rproxy.apply(reload=reload)
        except Exception as e:
            result["errors"].append(f"同步下载路由失败：{e}")
    return result


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
    else:
        real = os.path.join(config.BASE_DIR, name)
    os.makedirs(real, exist_ok=True)
    reg = _registry()
    reg.setdefault("apps", {})[name] = {
        "dir": real, "comment": comment or "",
        "deploy": {"domain": "", "ssl": {"mode": "none"}, "port": 0},
    }
    _save_registry(reg)
    _auto_sync()
    return get_app(name)


def remove_app(name):
    reg = _registry()
    if name not in reg.get("apps", {}):
        raise AppError(f"应用未注册：{name}")
    meta = reg["apps"].pop(name)
    _save_registry(reg)
    _auto_sync()
    return {"name": name, "removed": True, "dir": meta.get("dir", "")}


def backend_list():
    """反代后端概览：当前后端 + 各后端能力（切换/迁移 UI 与 CLI 用）。"""
    from ... import rproxy
    try:
        current = rproxy.backend_name()
    except Exception:
        current = None
    backends = []
    for name, info in sorted(rproxy.backends().items()):
        caps = info.get("capabilities") or []
        backends.append({"name": name, "plugin": info.get("plugin"),
                         "download_route": "download_route" in caps,
                         "clear_routes": "clear_routes" in caps})
    return {"backend": current, "backends": backends}


def switch_backend(backend=None, migrate=True, reload=True):
    """切换默认反代后端，并把下载路由/应用站点迁移过去。

    migrate=True 时先清空旧后端的托管下载短链（应用站点块与 WAF 段保留，
    切回即可恢复），再对新后端执行完整同步（应用站点块 + 版本短链 + latest）。
    """
    from ... import rproxy
    import importlib
    old = rproxy.backend_name()
    if backend:
        rproxy.set_backend(backend)
    new = rproxy.backend_name()
    result = {"backend": new, "previous": old, "cleared": None, "errors": []}
    if migrate and old and new != old:
        try:
            if rproxy.has_capability("clear_routes", old):
                info = rproxy.backends().get(old) or {}
                mod = importlib.import_module(info["module"]) if info.get("module") else None
                fn = getattr(mod, "clear_routes", None)
                if callable(fn):
                    result["cleared"] = fn(reload=True)
                else:
                    result["errors"].append(f"{old} 未实现 clear_routes()，旧路由保留")
            else:
                result["errors"].append(f"{old} 不支持 clear_routes 能力，旧路由保留")
        except Exception as e:
            result["errors"].append(f"清理旧后端路由失败：{e}")
    result["sync"] = sync_proxy_routes(reload=reload)
    return result


def _auto_sync():
    """注册/删除应用后自动同步反代路由（失败不阻断主流程）。"""
    try:
        sync_proxy_routes()
    except Exception:
        pass


# -------------------- CI 推送通知与待注册新项目 --------------------

def _ci_token_file():
    return os.path.join(config.CONF_DIR, "apps-ci-token")


def _watch_state_file():
    return os.path.join(config.CONF_DIR, "apps-watch.json")


def ci_token(reset=False):
    """CI 推送通知令牌：首次访问自动生成（存 CONF_DIR，0600）。"""
    path = _ci_token_file()
    if not reset:
        try:
            with open(path) as f:
                tok = f.read().strip()
            if tok:
                return tok
        except OSError:
            pass
    import secrets
    tok = secrets.token_hex(20)
    os.makedirs(config.CONF_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(tok)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return tok


def pending_apps():
    """未注册的新项目目录（BASE_DIR 下含 apk/jar/zip 的子目录）+ 监听状态。

    不自动注册：由面板提示用户勾选注册（全部或部分）。
    """
    disc = discover()
    return {"base": disc["base"], "candidates": disc["candidates"],
            "watch": _watch_read()}


def register_apps(names):
    """批量注册待注册目录（勾选部分或全选）；注册即自动同步反代路由。"""
    registered, errors = [], []
    for name in names or []:
        try:
            app = add_app(str(name))
            registered.append({"name": app["name"], "dir": app["dir"]})
        except Exception as e:
            errors.append(f"{name}: {e}")
    return {"registered": registered, "errors": errors}


def ci_notify(app=None):
    """CI 流水线推送后回调：立即同步下载路由（免轮询），并附带待注册提示。"""
    sync = sync_proxy_routes(reload=True)
    pend = pending_apps()
    return {"ok": not sync["errors"],
            "synced": bool(sync["data"]),
            "errors": sync["errors"],
            "pending": [c["name"] for c in pend["candidates"]]}


# ---- BASE_DIR 新目录监听（systemd path unit，不自动注册） ----

_WATCH_UNIT = "aups-appupdate-watch"


def _watch_read():
    try:
        with open(_watch_state_file()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def watch_status():
    """BASE_DIR 新目录监听状态（依赖 systemd，仅 Linux 实机）。"""
    import shutil as _sh
    if not _sh.which("systemctl"):
        return {"available": False, "enabled": False,
                "reason": "无 systemd（仅支持 Linux 实机部署）"}
    from ...util import run as _run
    enabled = _run(["systemctl", "is-enabled", _WATCH_UNIT + ".path"], check=False)
    active = _run(["systemctl", "is-active", _WATCH_UNIT + ".path"], check=False)
    return {"available": True, "enabled": enabled.returncode == 0,
            "active": active.returncode == 0, "base": config.BASE_DIR,
            "unit": _WATCH_UNIT + ".path", "last_event": _watch_read()}


def watch_enable():
    """安装并启用 path unit：BASE_DIR 出现新目录/文件变化时触发 watch trigger。"""
    import shutil as _sh
    from ...util import run as _run
    if not _sh.which("systemctl"):
        raise AppError("无 systemd（仅支持 Linux 实机部署）")
    base = os.path.realpath(config.BASE_DIR)
    os.makedirs(base, exist_ok=True)
    units = {
        _WATCH_UNIT + ".path": (
            "[Unit]\n"
            f"Description=AUPS appupdate: watch {base} for new project dirs\n\n"
            "[Path]\n"
            f"PathModified={base}\n"
            f"Unit={_WATCH_UNIT}.service\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        ),
        _WATCH_UNIT + ".service": (
            "[Unit]\n"
            f"Description=AUPS appupdate: handle new project dir in {base}\n\n"
            "[Service]\n"
            "Type=oneshot\n"
            "ExecStart=/usr/local/bin/aups plugins appupdate watch trigger\n"
        ),
    }
    for name, content in units.items():
        with open(os.path.join("/etc/systemd/system", name), "w") as f:
            f.write(content)
    _run(["systemctl", "daemon-reload"], check=True)
    _run(["systemctl", "enable", "--now", _WATCH_UNIT + ".path"], check=True)
    return watch_status()


def watch_disable():
    """停用并移除监听 unit。"""
    import shutil as _sh
    from ...util import run as _run
    if not _sh.which("systemctl"):
        raise AppError("无 systemd（仅支持 Linux 实机部署）")
    _run(["systemctl", "disable", "--now", _WATCH_UNIT + ".path"], check=False)
    for name in (_WATCH_UNIT + ".path", _WATCH_UNIT + ".service"):
        try:
            os.remove(os.path.join("/etc/systemd/system", name))
        except OSError:
            pass
    _run(["systemctl", "daemon-reload"], check=False)
    return watch_status()


def watch_trigger():
    """path unit 触发入口：记录事件快照并同步一次路由（不自动注册）。"""
    state = {"ts": int(time.time()), "base": config.BASE_DIR,
             "candidates": [c["name"] for c in discover()["candidates"]]}
    os.makedirs(config.CONF_DIR, exist_ok=True)
    tmp = _watch_state_file() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, _watch_state_file())
    sync = sync_proxy_routes(reload=True)
    return {"ok": True, "state": state, "sync_errors": sync["errors"]}


def app_dir(name):
    return get_app(name)["dir"]


# -------------------- 部署配置 --------------------

def set_deploy(name, **kwargs):
    """设置应用部署配置（domain/ssl/port/workdir/user/ci_user/ssh_key/proxy）。"""
    reg = _registry()
    meta = reg.get("apps", {}).get(name)
    if not meta:
        raise AppError(f"应用未注册：{name}")
    if kwargs.get("domain"):
        wanted = _norm_domain(kwargs["domain"])
        for other_name, other_meta in reg.get("apps", {}).items():
            if other_name != name and _norm_domain(_deploy(other_meta).get("domain")) == wanted:
                raise AppError(f"域名 {kwargs['domain']} 已被应用 {other_name} 使用")
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


def validate_domain(domain, workdir="", app_name=""):
    """新域名先做 DNS 预检；已同步域名再校验反代应用标识。"""
    import socket
    import urllib.request
    import urllib.error

    domain = (domain or "").strip()
    app_name = (app_name or "").strip()
    if not domain:
        return {"ok": False, "message": "域名不能为空"}
    if not app_name:
        return {"ok": False, "message": "缺少应用名称，无法校验反代归属"}
    saved_domain = ""
    if app_exists(app_name):
        saved_domain = _norm_domain(get_deploy(app_name).get("domain"))
    if saved_domain != _norm_domain(domain):
        try:
            addresses = sorted({item[4][0] for item in socket.getaddrinfo(domain, 80)})
        except (socket.gaierror, OSError):
            return {"ok": False, "message": f"域名 {domain} DNS 解析失败"}
        return {"ok": True, "preflight": True, "addresses": addresses,
                "message": f"域名 {domain} DNS 解析正常；保存后将自动同步并确认反代归属"}
    expected = f"aups-domain-verify:{app_name}"
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}/.well-known/aups-domain-check"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AUPS/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read(512).decode("utf-8", errors="replace").strip()
                if body == expected:
                    return {"ok": True, "message": f"域名 {domain} 已指向本机应用 {app_name}"}
        except (urllib.error.URLError, OSError):
            continue
    return {"ok": False, "message":
            f"域名 {domain} 未通过反代校验；请先保存配置并同步反代路由"}


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


# -------------------- 更新日志（版本 changelog） --------------------

def _changelog_file():
    return os.path.join(config.CONF_DIR, "apps-changelog.json")


def _load_changelogs():
    """{应用名: {版本: 日志文本}}；文件缺失/损坏返回空。"""
    try:
        with open(_changelog_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_changelogs(data):
    os.makedirs(config.CONF_DIR, exist_ok=True)
    tmp = _changelog_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _changelog_file())


def list_changelogs(name):
    """某应用的全部更新日志 {版本: 文本}（CI 直传的版本天然无记录）。"""
    app_dir(name)
    logs = _load_changelogs().get(name, {})
    return {k: v for k, v in logs.items() if isinstance(v, str)}


def get_changelog(name, version):
    """读取某应用某版本的更新日志；无记录返回空串。"""
    logs = list_changelogs(name)
    return logs.get(str(version), "")


def set_changelog(name, version, text):
    """写入/更新某应用某版本的更新日志；清空文本即删除该条记录。"""
    app_dir(name)
    version = str(version or "").strip()
    if not version:
        raise AppError("版本号不能为空")
    data = _load_changelogs()
    app_notes = data.setdefault(name, {})
    text = str(text or "").replace("\r\n", "\n").strip()
    if text:
        app_notes[version] = text
    else:
        app_notes.pop(version, None)
        if not app_notes:
            data.pop(name, None)
    _save_changelogs(data)
    return {"name": name, "version": version, "changelog": text}


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
        result = rproxy.apply(reload=reload)
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
    return rproxy.preview().get("apps", "")


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
