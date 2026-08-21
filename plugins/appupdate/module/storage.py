import os

from ... import config
from ...errors import AppError
from ...util import run


def _app_of(path):
    """根据已注册应用，返回 APK 所属应用名（路径前缀匹配）。"""
    from . import apps
    real = os.path.realpath(path)
    for app in apps.list_apps():
        d = os.path.realpath(app["dir"])
        if real == d or real.startswith(d + os.sep):
            return app["name"]
    return None


def usage():
    base = config.BASE_DIR
    apps = []
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            p = os.path.join(base, entry)
            if not os.path.isdir(p):
                continue
            du = run(["du", "-sb", p])
            size = int(du.stdout.split()[0]) if du.returncode == 0 else 0
            apps.append({"app": entry, "path": p, "size_bytes": size,
                         "size_mb": round(size / 1048576, 1)})
    total = 0
    if os.path.isdir(base):
        du = run(["du", "-sb", base])
        total = int(du.stdout.split()[0]) if du.returncode == 0 else 0
    return {"base": base, "total_bytes": total, "total_mb": round(total / 1048576, 1),
            "apps": apps}


def quota_status():
    """存储用量 + 配额（总配额 + 各应用配额/用量）。"""
    from . import apps
    u = usage()
    app_rows = []
    for a in apps.list_apps():
        d = os.path.realpath(a["dir"])
        size = 0
        if os.path.isdir(d):
            du = run(["du", "-sb", d])
            if du.returncode == 0:
                try:
                    size = int(du.stdout.split()[0])
                except (ValueError, IndexError):
                    size = 0
        quota = a["quota_mb"]
        app_rows.append({"name": a["name"], "dir": d, "quota_mb": quota,
                         "size_bytes": size, "size_mb": round(size / 1048576, 1),
                         "over": bool(quota and size > quota * 1048576)})
    return {"base": u["base"], "total_bytes": u["total_bytes"],
            "total_mb": u["total_mb"], "total_quota_mb": apps.get_total_quota(),
            "apps": app_rows}


def apks():
    from . import apps
    base = config.BASE_DIR
    result = []
    lockmap = {a["name"]: set(a.get("locked", [])) for a in apps.list_apps()}
    if os.path.isdir(base):
        res = run(["find", base, "-type", "f", "-name", "*.apk"])
        for line in res.stdout.splitlines():
            path = line.strip()
            if not path:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            app = _app_of(path)
            version = apps.parse_version(os.path.basename(path)) if app else None
            locked = bool(app and version and version in lockmap.get(app, set()))
            result.append({"path": path, "app": app, "version": version, "locked": locked,
                           "size_bytes": st.st_size, "size_mb": round(st.st_size / 1048576, 1)})
    result.sort(key=lambda a: a["size_bytes"], reverse=True)
    return result


def delete_apk(paths):
    base = os.path.realpath(config.BASE_DIR)
    from . import apps
    app_bases = [os.path.realpath(a["dir"]) for a in apps.list_apps()]
    removed = []
    for p in paths:
        real = os.path.realpath(p)
        if not os.path.isfile(real):
            if not os.path.isabs(p):
                found = False
                for ab in app_bases:
                    candidate = os.path.join(ab, p)
                    if os.path.isfile(candidate):
                        real = candidate
                        found = True
                        break
                if not found:
                    raise AppError(f"文件不存在：{p}")
            else:
                raise AppError(f"文件不存在：{p}")
        if not real.startswith(base + os.sep) or not real.lower().endswith(".apk"):
            raise AppError(f"只允许删除 {base}/ 下的 .apk 文件：{p}")
        os.remove(real)
        removed.append(real)
    return removed
