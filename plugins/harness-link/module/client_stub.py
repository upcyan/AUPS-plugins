#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness Link 客户端（零依赖，仅 Python 标准库）。

运行在 DeepSeek Harness 一侧，与 AUPS 面板 harness-link 插件建立授权连接。

用法：
  注册配对   python harness_link_client.py register --server http://面板地址:端口 --token 配对令牌 [--name 名称] [--meta JSON]
  监听消息   python harness_link_client.py listen [--wait 15]
  回复面板   python harness_link_client.py send --text "回复内容"
  心跳探活   python harness_link_client.py status

说明：
- register 成功后连接凭证保存到状态文件（默认 ~/.harness_link.json），
  之后 listen/send/status 自动读取，无需重复配对；
- listen 把收到的面板消息按 "[msg_id] 内容" 打印到 stdout 并即时刷新，
  可作为常驻进程被上层程序（如 Harness 工具任务）捕获输出；
- 会话密钥等同连接身份，请勿泄露；在面板吊销连接后立即失效。
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_STATE = os.path.join(os.path.expanduser("~"), ".harness_link.json")


def _req(method, url, payload=None, key=None, timeout=40):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if key:
        r.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail", "")
        except Exception:
            detail = getattr(e, "reason", str(e))
        print("[hlink] HTTP %s: %s" % (e.code, detail), file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print("[hlink] 无法连接服务器: %s" % e.reason, file=sys.stderr)
        sys.exit(3)


def _load_state(path):
    if not os.path.isfile(path):
        print("[hlink] 状态文件不存在，请先执行 register 配对：%s" % path, file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        st = json.load(f)
    if not st.get("session_key"):
        print("[hlink] 状态文件缺少 session_key，请重新 register", file=sys.stderr)
        sys.exit(1)
    return st


def _base(server):
    return (server or "").rstrip("/")


def cmd_register(a):
    meta = {}
    if a.meta:
        try:
            meta = json.loads(a.meta)
        except ValueError:
            print("[hlink] --meta 不是合法 JSON", file=sys.stderr)
            sys.exit(1)
    d = _req("POST", _base(a.server) + "/api/hlink/connector/register",
             {"name": a.name, "meta": meta}, key=a.token)
    state = {"server": _base(a.server), "conn_id": d["conn_id"],
             "session_key": d["session_key"]}
    tmp = a.state + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, a.state)
    print("[hlink] 已连接：%s（凭证已存 %s）" % (d["conn_id"], a.state))


def cmd_listen(a):
    st = _load_state(a.state)
    url = _base(st["server"]) + "/api/hlink/connector/poll?wait=%d" % max(0, min(a.wait, 25))
    print("[hlink] 开始监听（Ctrl+C 退出）...", flush=True)
    while True:
        try:
            d = _req("GET", url, key=st["session_key"],
                     timeout=min(a.wait, 25) + 15)
        except SystemExit:
            raise
        for m in d.get("messages") or []:
            print("[%s] %s" % (m.get("id"), m.get("text", "")), flush=True)


def cmd_send(a):
    st = _load_state(a.state)
    d = _req("POST", _base(st["server"]) + "/api/hlink/connector/reply",
             {"text": a.text}, key=st["session_key"])
    print("[hlink] 已回复（msg_id=%s）" % d.get("id"))


def cmd_status(a):
    st = _load_state(a.state)
    d = _req("POST", _base(st["server"]) + "/api/hlink/connector/heartbeat",
             {}, key=st["session_key"])
    print("[hlink] 在线（心跳窗口 %ss）" % d.get("online_window"))


def main():
    p = argparse.ArgumentParser(description="Harness Link 客户端")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("register", help="首次配对注册")
    sp.add_argument("--server", required=True, help="面板地址，如 http://1.2.3.4:8000")
    sp.add_argument("--token", required=True, help="接入授权页显示的配对令牌")
    sp.add_argument("--name", default="harness-client", help="连接名称")
    sp.add_argument("--meta", default="", help='附加元数据 JSON，如 \'{"os":"win"}\'')
    sp.add_argument("--state", default=DEFAULT_STATE)
    sp.set_defaults(fn=cmd_register)

    sp = sub.add_parser("listen", help="长轮询监听面板消息")
    sp.add_argument("--wait", type=int, default=15, help="长轮询秒数（<=25）")
    sp.add_argument("--state", default=DEFAULT_STATE)
    sp.set_defaults(fn=cmd_listen)

    sp = sub.add_parser("send", help="回复面板一条消息")
    sp.add_argument("--text", required=True)
    sp.add_argument("--state", default=DEFAULT_STATE)
    sp.set_defaults(fn=cmd_send)

    sp = sub.add_parser("status", help="心跳探活")
    sp.add_argument("--state", default=DEFAULT_STATE)
    sp.set_defaults(fn=cmd_status)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
