import os

from ... import config
from ...errors import AppError
from ...util import run


def _ssh_dir(user):
    if user == "root":
        return "/root/.ssh"
    return f"/home/{user}/.ssh"


def _keyfile(user):
    return os.path.join(_ssh_dir(user), "authorized_keys")


def list_keys(user):
    path = _keyfile(user)
    keys = []
    if not os.path.isfile(path):
        return keys
    with open(path) as f:
        for i, line in enumerate(f.read().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            keys.append({
                "index": i,
                "type": parts[0] if parts else "?",
                "comment": parts[-1] if len(parts) > 2 else "",
                "key": line,
            })
    return keys


def add_key(user, key, comment=""):
    key = (key or "").strip()
    if not key:
        raise AppError("SSH 公钥为空")
    if not key.startswith(("ssh-", "ecdsa-", "sk-", "rsa-")):
        raise AppError("公钥格式不正确（应以 ssh-ed25519 / ssh-rsa 等开头）")
    sshdir = _ssh_dir(user)
    run(["mkdir", "-p", sshdir])
    run(["chmod", "700", sshdir])
    if user != "root":
        run(["chown", f"{user}:{user}", sshdir], check=True)
    path = _keyfile(user)
    if not os.path.exists(path):
        open(path, "w").close()
    run(["chmod", "600", path])
    if user != "root":
        run(["chown", f"{user}:{user}", path], check=True)
    with open(path) as f:
        existing = set(f.read().splitlines())
    if key not in existing:
        with open(path, "a") as f:
            f.write(key + "\n")
        return {"user": user, "added": True, "key": key[:50] + "..."}
    return {"user": user, "added": False, "key": key[:50] + "..."}


def remove_key(user, index):
    keys = list_keys(user)
    if not (1 <= index <= len(keys)):
        raise AppError(f"索引越界：1-{len(keys)}，收到 {index}")
    target = keys[index - 1]["key"]
    path = _keyfile(user)
    with open(path) as f:
        lines = f.readlines()
    with open(path, "w") as f:
        for line in lines:
            if line.strip() != target:
                f.write(line)
    return {"user": user, "removed_index": index, "key": target[:50] + "..."}
