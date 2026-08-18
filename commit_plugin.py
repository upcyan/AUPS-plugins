# -*- coding: utf-8 -*-
"""插件提交辅助脚本：自动检测改动的插件，重算 index.json 哈希，提交并推送。

用法：
    python commit_plugin.py <插件名> [提交信息]
    python commit_plugin.py appupdate "feat: 新增XX功能"
    python commit_plugin.py caddy "fix: 修复XX问题"

流程：
    1. git add 插件目录下所有文件
    2. 运行 gen_index_hashes.py 重算 index.json（自动同步版本号）
    3. git add index.json
    4. git commit（提交信息 + [skip ci]）
    5. git push
"""
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.dirname(__file__) or ".")
SCRIPTS = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "opencode")
GEN_HASH = os.path.join(SCRIPTS, "gen_index_hashes.py")


def run(cmd, **kw):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, **kw)
    return r


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

    # 1. git add 插件文件
    print(f"[1/5] git add {plugin_dir}/")
    r = run(["git", "add", f"{plugin_dir}/"])
    if r.returncode != 0:
        print(f"  git add 失败: {r.stderr}")
        sys.exit(1)

    # 2. 重算 index.json 哈希（自动同步版本号）
    print(f"[2/5] 重算 index.json 哈希...")
    if os.path.isfile(GEN_HASH):
        r = run(["python", GEN_HASH, REPO])
        print(f"  {r.stdout.strip()}")
    else:
        print(f"  警告: {GEN_HASH} 不存在，跳过哈希重算")
        print(f"  请手动运行: python gen_index_hashes.py {REPO}")

    # 3. git add index.json
    print("[3/5] git add index.json")
    r = run(["git", "add", "index.json"])

    # 4. git commit
    print(f"[4/5] git commit: {msg}")
    r = run(["git", "commit", "-m", msg])
    if r.returncode != 0:
        print(f"  提交失败或无改动: {r.stderr.strip() or r.stdout.strip()}")
        sys.exit(0)  # 无改动不算错误
    print(f"  {r.stdout.strip()}")

    # 5. git push
    print("[5/5] git push")
    r = run(["git", "push", "origin", "main"])
    if r.returncode != 0:
        print(f"  推送失败: {r.stderr}")
        sys.exit(1)
    print(f"  {r.stdout.strip()}")
    print("\n完成！")


if __name__ == "__main__":
    main()
