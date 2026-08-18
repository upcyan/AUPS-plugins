# -*- coding: utf-8 -*-
"""插件提交辅助脚本：自动 bump 版本、重算 index.json 哈希、提交并推送。

用法：
    python commit_plugin.py <插件名> [提交信息]
    python commit_plugin.py appupdate "feat: 新增XX功能"
    python commit_plugin.py caddy "fix: 修复XX问题"

流程：
    1. 自动 bump manifest.py/manifest.json 版本号（patch +1）
    2. git add 插件目录下所有文件
    3. 运行 gen_index_hashes.py 重算 index.json（自动同步版本号）
    4. git add index.json
    5. git commit
    6. git push
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

    # 读取当前版本
    with open(manifest_py, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', content)
    if not m:
        print(f"  警告: 无法从 manifest.py 解析版本号，跳过 bump")
        return
    old_ver = m.group(1)
    parts = old_ver.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    new_ver = ".".join(parts)

    # 更新 manifest.py
    content = content.replace(f'"version": "{old_ver}"', f'"version": "{new_ver}"', 1)
    with open(manifest_py, "w", encoding="utf-8") as f:
        f.write(content)

    # 更新 manifest.json
    if os.path.isfile(manifest_json):
        with open(manifest_json, encoding="utf-8") as f:
            data = json.load(f)
        data["version"] = new_ver
        with open(manifest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print(f"  版本: {old_ver} → {new_ver}")
    return new_ver


def main():
    if len(sys.argv) < 3:
        print("用法: python commit_plugin.py <插件名> \"提交信息\"")
        print("示例: python commit_plugin.py appupdate \"feat: 新增XX功能\"")
        sys.exit(1)

    name = sys.argv[1]
    msg = sys.argv[2]
    plugin_dir = f"plugins/{name}"

    if not os.path.isdir(os.path.join(REPO, plugin_dir)):
        print(f"错误: 插件目录不存在: {plugin_dir}")
        sys.exit(1)

    # 1. 自动 bump 版本号
    print(f"[1/6] 自动 bump 版本...")
    new_ver = bump_version(name)

    # 2. git add 插件文件
    print(f"[2/6] git add {plugin_dir}/")
    r = run(["git", "add", f"{plugin_dir}/"])

    # 3. 重算 index.json 哈希（自动同步版本号）
    print(f"[3/6] 重算 index.json 哈希...")
    if os.path.isfile(GEN_HASH):
        r = run(["python", GEN_HASH, REPO])
        print(f"  {r.stdout.strip()}")

    # 4. 验证哈希一致性
    print("[4/6] 验证哈希一致性...")
    verify_script = os.path.join(REPO, "verify_hashes.py")
    if os.path.isfile(verify_script):
        r = run(["python", verify_script, REPO])
        print(f"  {r.stdout.strip()}")
        if r.returncode != 0:
            print("  哈希验证失败，终止提交")
            sys.exit(1)

    # 5. git add index.json + commit
    print("[5/6] git commit")
    run(["git", "add", "index.json"])
    r = run(["git", "commit", "-m", msg])
    if r.returncode != 0:
        print(f"  提交失败或无改动: {r.stderr.strip() or r.stdout.strip()}")
        sys.exit(0)
    print(f"  {r.stdout.strip()}")

    # 6. git push
    print("[6/6] git push")
    r = run(["git", "push", "origin", "main"])
    if r.returncode != 0:
        print(f"  推送失败: {r.stderr}")
        sys.exit(1)
    print(f"  {r.stdout.strip()}")
    print(f"\n完成！版本 {new_ver} 已推送")


if __name__ == "__main__":
    main()
