# -*- coding: utf-8 -*-
"""插件提交辅助脚本：自动 bump 版本、重算 index.json 哈希、提交并推送。

用法：
    python commit_plugin.py <插件名> [提交信息]
    python commit_plugin.py appupdate "feat: 新增XX功能"

流程：
    1. 自动 bump manifest.py/manifest.json 版本号（patch +1）
    2. git add + commit 插件文件
    3. 运行 gen_index_hashes.py 从 git blob 重算 index.json 哈希
    4. git add index.json + commit
    5. git push
"""
import json
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.dirname(__file__) or ".")
SCRIPTS = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "opencode")
GEN_HASH = os.path.join(SCRIPTS, "gen_index_hashes.py")


def run(cmd, **kw):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, **kw)
    return r


def bump_version(name):
    """自动 bump 插件版本号（patch +1），同步 manifest.py / manifest.json。"""
    manifest_py = os.path.join(REPO, f"plugins/{name}/module/manifest.py")
    manifest_json = os.path.join(REPO, f"plugins/{name}/manifest.json")
    with open(manifest_py, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', content)
    if not m:
        print(f"  警告: 无法解析版本号，跳过 bump")
        return
    old_ver = m.group(1)
    parts = old_ver.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    new_ver = ".".join(parts)
    content = content.replace(f'"version": "{old_ver}"', f'"version": "{new_ver}"', 1)
    with open(manifest_py, "w", encoding="utf-8") as f:
        f.write(content)
    if os.path.isfile(manifest_json):
        with open(manifest_json, encoding="utf-8") as f:
            data = json.load(f)
        data["version"] = new_ver
        with open(manifest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"  版本: {old_ver} -> {new_ver}")
    return new_ver


def main():
    if len(sys.argv) < 3:
        print("用法: python commit_plugin.py <插件名> \"提交信息\"")
        sys.exit(1)

    name = sys.argv[1]
    msg = sys.argv[2]
    plugin_dir = f"plugins/{name}"

    if not os.path.isdir(os.path.join(REPO, plugin_dir)):
        print(f"错误: 插件目录不存在: {plugin_dir}")
        sys.exit(1)

    # 1. bump 版本
    print(f"[1/5] bump 版本...")
    new_ver = bump_version(name)

    # 2. git add + commit 插件文件（先提交，后续才能从 git blob 算哈希）
    print(f"[2/5] git add + commit 插件文件...")
    run(["git", "add", f"{plugin_dir}/"])
    r = run(["git", "commit", "-m", msg])
    if r.returncode != 0:
        print(f"  提交失败: {r.stderr.strip()}")
        sys.exit(1)

    # 3. 从 git blob 重算 index.json 哈希
    print(f"[3/5] 重算 index.json 哈希...")
    if os.path.isfile(GEN_HASH):
        r = run(["python", GEN_HASH, REPO])
        print(f"  {r.stdout.strip()}")

    # 4. 验证哈希
    print("[4/5] 验证哈希...")
    verify_script = os.path.join(REPO, "verify_hashes.py")
    if os.path.isfile(verify_script):
        r = run(["python", verify_script, REPO])
        print(f"  {r.stdout.strip()}")
        if r.returncode != 0:
            print("  哈希验证失败，终止")
            sys.exit(1)

    # 5. git add index.json + commit + push
    print("[5/5] commit + push index.json")
    run(["git", "add", "index.json"])
    r = run(["git", "commit", "-m", f"chore: index.json {name} v{new_ver}"])
    if r.returncode == 0:
        r = run(["git", "push", "origin", "main"])
        if r.returncode != 0:
            print(f"  推送失败: {r.stderr}")
            sys.exit(1)
        print(f"  已推送 {name} v{new_ver}")
    else:
        print("  index.json 无变更")


if __name__ == "__main__":
    main()
