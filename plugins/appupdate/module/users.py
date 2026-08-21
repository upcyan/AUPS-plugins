import json
import os

from ... import config
from ...errors import AppError
from ...util import has_cmd, run


def _ensure_acl():
    if has_cmd("setfacl"):
        return
    if has_cmd("apt-get"):
        run(["apt-get", "update", "-y"])
        run(["apt-get", "install", "-y", "acl"], check=True)
    elif has_cmd("dnf") or has_cmd("yum"):
        run([("dnf" if has_cmd("dnf") else "yum"), "install", "-y", "acl"], check=True)
    else:
        raise AppError("未能自动安装 acl，请手动本机安装后重试")
    if not has_cmd("setfacl"):
        raise AppError("ACL 工具(setfacl)不可用")


def _safe_dir(path):
    base = os.path.realpath(config.BASE_DIR)
    real = os.path.realpath(path)
    if real == base or not real.startswith(base + os.sep):
        raise AppError(f"只能授权 {base}/ 下的目录：{path}")
    return real


def ensure_dir(path):
    """校验目录位于应用根目录下并创建，避免以 root 在任意路径落盘。"""
    real = _safe_dir(path)
    os.makedirs(real, exist_ok=True)
    return real


def _validate_dir(path):
    real = _safe_dir(path)
    if not os.path.isdir(real):
        raise AppError(f"目录不存在：{path}")
    return real


def _registry():
    path = config.USERS_FILE
    if os.path.isfile(path):
        try:
            return json.load(open(path))
        except (OSError, ValueError):
            pass
    return {}


def _save_registry(reg):
    os.makedirs(config.CONF_DIR, exist_ok=True)
    with open(config.USERS_FILE, "w") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def list_users():
    reg = _registry().get("users", {})
    return [
        {"name": name, "comment": meta.get("comment", ""), "dirs": list_dir_access(name)}
        for name, meta in reg.items()
    ]


def user_exists(name):
    return run(["id", name]).returncode == 0


def create_user(name, comment="", key=None):
    _ensure_acl()
    if user_exists(name):
        raise AppError(f"用户已存在：{name}")
    run(["useradd", "-m", "-s", "/bin/bash", name], check=True)
    run(["passwd", "-l", name], check=True)  # 锁定密码，仅允许密钥登录
    if key:
        from .sshkeys import add_key
        add_key(name, key)
    reg = _registry()
    reg.setdefault("users", {})[name] = {"comment": comment or ""}
    _save_registry(reg)
    return {"name": name, "created": True}


def remove_user(name):
    if name in ("root", "", "update-server"):
        raise AppError(f"禁止删除受保护用户：{name}")
    # 先撤掉其所有目录 ACL
    for d in list_dir_access(name):
        try:
            revoke_dir(name, d)
        except AppError:
            pass
    run(["userdel", "-r", name])  # 不存在时 userdel 失败但不致命
    reg = _registry()
    reg.get("users", {}).pop(name, None)
    _save_registry(reg)
    return {"name": name, "removed": True}


def grant_dir(user, path):
    real = _validate_dir(path)
    if not user_exists(user):
        raise AppError(f"用户不存在：{user}")
    _ensure_acl()
    run(["setfacl", "-Rm", f"u:{user}:rwX", real], check=True)
    run(["setfacl", "-Rdm", f"u:{user}:rwX", real], check=True)
    return {"user": user, "dir": real, "granted": True}


def revoke_dir(user, path):
    real = _validate_dir(path)
    run(["setfacl", "-R", "-x", f"u:{user}", real])
    run(["setfacl", "-R", "-x", f"d:u:{user}", real])
    return {"user": user, "dir": real, "revoked": True}


def list_dir_access(user):
    base = os.path.realpath(config.BASE_DIR)
    found = []
    if not os.path.isdir(base):
        return found
    for root, dirs, files in os.walk(base):
        g = run(["getfacl", "-p", "--absolute-names", root])
        if g.returncode == 0 and f"user:{user}:" in g.stdout:
            found.append(root)
    return found
