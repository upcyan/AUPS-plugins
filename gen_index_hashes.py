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


def _git(*args):
    """在仓库内执行 git，显式声明 safe.directory。

    仓库属主与当前用户不同时，git 会以 dubious ownership 拒绝一切操作；
    此前该失败被静默吞掉，退化成读取工作区原文（CRLF），算出的哈希与服务器
    实际下载的 blob（LF）不符，导致市场安装一律报「插件包完整性校验失败」。
    """
    return subprocess.run(["git", "-c", "safe.directory=" + REPO, "-C", REPO, *args],
                          capture_output=True)


def blob_bytes(rel):
    """取 git 仓库中已提交的内容（LF），与市场下载的 codeload tarball 完全一致。"""
    p = _git("show", "HEAD:plugins/%s/%s" % (NAME, rel))
    if p.returncode == 0:
        return p.stdout
    # 未跟踪/未提交的文件没有 blob；用 LF 规范化后的工作区内容近似，
    # 避免把 CRLF 字节写进索引（.gitattributes 强制 eol=lf）。
    with open(os.path.join(PLUGINS, NAME, rel.replace("/", os.sep)), "rb") as f:
        raw = f.read()
    return raw.replace(b"\r\n", b"\n")


def collect(name):
    root = os.path.join(PLUGINS, name)
    files = {}
    for base, _dirs, names in os.walk(root):
        for fn in sorted(names):
            if fn.endswith('.pyc') or fn == '__pycache__':
                continue
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if '__pycache__' in rel:
                continue
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
    entries = data.setdefault("plugins", [])
    known = {p.get("name") for p in entries}
    for name in sorted(os.listdir(PLUGINS)):
        pdir = os.path.join(PLUGINS, name)
        if name in known or not os.path.isdir(pdir):
            continue
        outer = os.path.join(pdir, "manifest.json")
        try:
            with open(outer, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            print(f"WARN: plugins/{name} 缺少有效 manifest.json，跳过")
            continue
        man = read_manifest(name)
        entry = {
            "name": name,
            "title": meta.get("title") or man.get("title") or name,
            "attr": meta.get("attr") or man.get("attr") or "功能",
            "version": meta.get("version") or man.get("version") or "0.0.0",
            "description": meta.get("description") or man.get("description") or "",
        }
        if man.get("depends"):
            entry["depends"] = man["depends"]
        entries.append(entry)
        known.add(name)
        print(f"ADD {name}: 已加入市场索引")
    changed = 0
    for p in entries:
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
        if man.get("depends"):
            p["depends"] = man["depends"]
        else:
            p.pop("depends", None)
        if man.get("version"):
            p["version"] = man["version"]
        if diffs:
            changed += 1
            print(f"UPD {name}: {len(diffs)} 个文件哈希已变更")
        else:
            print(f"OK  {name}: {len(p['files'])} 个文件（无变化）")
    # 固定市场下载提交：branch 字段写当前 HEAD SHA（codeload 按 SHA 的 tarball
    # 不可变，避免分支压缩包 CDN 缓存导致全量哈希不一致）。脚本在 index 提交
    # 前运行，HEAD 的 plugins/ 树与最终提交一致。
    head = _git("rev-parse", "HEAD")
    if head.returncode == 0:
        sha = head.stdout.decode().strip()
        if data.get("branch") != sha:
            data["branch"] = sha
            changed += 1
            print(f"PIN branch -> {sha}")
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n已更新 index.json（{changed} 个插件有变更）")


if __name__ == "__main__":
    main()
