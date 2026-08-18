# -*- coding: utf-8 -*-
"""验证 index.json 中所有插件的哈希是否与 git blob 一致。

用法：python verify_hashes.py [仓库路径]
"""
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
INDEX = os.path.join(REPO, "index.json")


def blob_hash(repo, name, rel):
    r = subprocess.run(
        ["git", "-C", repo, "show", f"HEAD:plugins/{name}/{rel}"],
        capture_output=True)
    if r.returncode != 0:
        return None
    return hashlib.sha256(r.stdout).hexdigest()


def main():
    with open(INDEX, encoding="utf-8") as f:
        data = json.load(f)
    errors = []
    for p in data.get("plugins", []):
        name = p["name"]
        for rel, expected in (p.get("files") or {}).items():
            got = blob_hash(REPO, name, rel)
            if not got:
                errors.append(f"{name}/{rel}: 文件不在 git 中")
            elif got != expected:
                errors.append(f"{name}/{rel}: 哈希不一致")
    if errors:
        print("❌ 发现哈希不一致：")
        for e in errors:
            print(f"  {e}")
        print(f"\n请运行: python gen_index_hashes.py {REPO}")
        sys.exit(1)
    else:
        print("✅ 所有插件哈希一致")
        sys.exit(0)


if __name__ == "__main__":
    main()
