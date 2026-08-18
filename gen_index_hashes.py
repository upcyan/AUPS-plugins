# -*- coding: utf-8 -*-
"""生成插件仓库 index.json 中每个插件的 files.sha256 哈希映射。"""
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
INDEX = os.path.join(REPO, "index.json")
PLUGINS = os.path.join(REPO, "plugins")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_bytes(rel):
    """取 git 仓库中已提交的内容（LF），与市场下载的 codeload tarball 完全一致。"""
    p = subprocess.run(
        ["git", "-C", REPO, "show", "HEAD:plugins/%s/%s" % (NAME, rel)],
        capture_output=True)
    if p.returncode == 0:
        return p.stdout
    # 未跟踪/未提交的文件：退化为工作区原文
    with open(os.path.join(PLUGINS, NAME, rel.replace("/", os.sep)), "rb") as f:
        return f.read()


def collect(name):
    root = os.path.join(PLUGINS, name)
    files = {}
    for base, _dirs, names in os.walk(root):
        for fn in sorted(names):
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            files[rel] = sha256(blob_bytes(rel))
    return files


def read_manifest(name):
    """读取插件 module/manifest.py 中的 MANIFEST dict（用于派生 cards/provides）。"""
    ns = {}
    mf = os.path.join(PLUGINS, name, "module", "manifest.py")
    try:
        with open(mf, encoding="utf-8") as f:
            exec(compile(f.read(), mf, "exec"), ns)
    except BaseException:
        return {}
    man = ns.get("MANIFEST")
    return man if isinstance(man, dict) else {}


def main():
    global NAME
    with open(INDEX, encoding="utf-8") as f:
        data = json.load(f)
    changed = 0
    for p in data.get("plugins", []):
        name = p["name"]
        pdir = os.path.join(PLUGINS, name)
        if not os.path.isdir(pdir):
            print(f"WARN: plugins/{name} 不存在，跳过")
            continue
        global NAME
        NAME = name
        old_files = p.get("files", {})
        new_files = collect(name)
        # 检测哈希变化
        diffs = [f for f in new_files if new_files[f] != old_files.get(f)]
        p["files"] = new_files
        man = read_manifest(name)
        p["cards"] = bool(man.get("cards"))
        p["provides"] = sorted((man.get("provides") or {}).keys())
        if man.get("version"):
            p["version"] = man["version"]
        if diffs:
            changed += 1
            print(f"UPD {name}: {len(diffs)} 个文件哈希已变更")
        else:
            print(f"OK  {name}: {len(p['files'])} 个文件（无变化）")
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n已更新 index.json（{changed} 个插件有变更）")


if __name__ == "__main__":
    main()
