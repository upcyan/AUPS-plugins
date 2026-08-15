"""cyansecengine 实时防护（Phase 3）：fanotify 文件监听 + YARA 命中 + 主动防御联动 WAF。

- fanotify（Linux 内核 API，ctypes 直调，无常驻第三方依赖）：监听配置路径树内
  写入/创建/移动事件；命中后对文件跑 YARA 规则（复用 subscribe 下载的规则）。
  若 fanotify 不可用（内核/权限），自动回退为轮询扫描（间隔可配）。
- 命中处理：
    1. 记录告警（data/cyansecengine/rt_events.json）
    2. 主动防御联动核心 WAF：为核心 WAF 添加 path_regex 拦截规则
      （waf.on_change 自动通知支持 waf 能力的反代 reload）
    3. 可选：把命中文件移入隔离目录
- 守护进程：插件生成脚本 → nohup 后台运行（/var/run/cyansec-rt.pid），需 root。
  单线程、内存占用极低，适配小内存 VPS。
"""

import ctypes
import ctypes.util
import json
import os
import re
import signal
import shutil
import subprocess
import time

from ... import config
from ...errors import AppError

DATA_DIR = os.path.join(config.PANEL_DATA_DIR, "cyansecengine")
RULES_DIR = os.path.join(DATA_DIR, "rules")
QUARANTINE_DIR = os.path.join(DATA_DIR, "quarantine")
RT_CONF = os.path.join(DATA_DIR, "rt.conf")
RT_EVENTS = os.path.join(DATA_DIR, "rt_events.json")
PID_FILE = "/var/run/cyansec-rt.pid"

# fanotify 常量（Linux kernel）
FAN_CLOSE_WRITE = 0x08
FAN_MOVED_TO = 0x80
FAN_CREATE = 0x100
FAN_EVENT_ON_CHILD = 0x08000000
FAN_CLOEXEC = 0x00000001
FAN_CLASS_NOTIF = 0x00000000
FAN_MARK_ADD = 0x00000001
FAN_MARK_MOUNT = 0x00000010

# struct fanotify_event_metadata（x86_64）：len=24
_FAN_META = ctypes.c_char * 24
_OFF_MASK = 8
_OFF_FD = 16

_SKIP_EXT = (".swp", ".swx", ".tmp", ".lock", "~", ".bak")
# 实时防护默认监控的脚本/Webshell 扩展名
_SCAN_EXTS = ("php", "jsp", "jspx", "asp", "aspx", "sh", "pl", "py", "cgi", "shtml")


def rt_status():
    """实时防护当前状态。"""
    conf = _load_conf()
    running = _daemon_running()
    return {
        "enabled": bool(conf.get("enabled")),
        "running": running,
        "pid": _read_pid(),
        "paths": conf.get("paths", []),
        "quarantine": bool(conf.get("quarantine", True)),
        "waf_block": bool(conf.get("waf_block", True)),
        "interval": conf.get("interval", 5),
        "events_dir": DATA_DIR,
    }


def _load_conf():
    try:
        with open(RT_CONF, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            return d
    except (OSError, ValueError):
        pass
    return {"enabled": False, "paths": [], "quarantine": True,
            "waf_block": True, "interval": 5}


def _save_conf(conf):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RT_CONF, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)


def set_rt(enabled, paths=None, quarantine=None, waf_block=None, interval=None):
    """开启/关闭实时防护配置。开启时写配置并启动守护进程。"""
    conf = _load_conf()
    conf["enabled"] = bool(enabled)
    if paths is not None:
        conf["paths"] = [p for p in paths if os.path.isdir(p)]
    if quarantine is not None:
        conf["quarantine"] = bool(quarantine)
    if waf_block is not None:
        conf["waf_block"] = bool(waf_block)
    if interval is not None:
        conf["interval"] = max(2, int(interval))
    _save_conf(conf)
    if enabled:
        _start_daemon()
    else:
        _stop_daemon()
    return rt_status()


# ---------- 守护进程控制 ----------

def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _daemon_running():
    pid = _read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _start_daemon():
    import sys
    if _daemon_running():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    script = os.path.join(DATA_DIR, "rt_daemon.py")
    src = _daemon_script()
    with open(script, "w", encoding="utf-8") as f:
        f.write(src)
    proc = subprocess.Popen([sys.executable, script],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, close_fds=True)
    for _ in range(25):
        time.sleep(0.2)
        if _daemon_running():
            return
    raise AppError("实时防护守护进程启动失败，请检查 root 权限与内核支持")


def _stop_daemon():
    pid = _read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _daemon_script():
    """生成守护进程脚本（填充面板路径占位符）。"""
    return _DAEMON_TEMPLATE.format(
        pkg_root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        panel_home=config.PANEL_HOME,
        conf_dir=config.CONF_DIR,
        data_dir=config.PANEL_DATA_DIR,
        conf_file=RT_CONF,
        pid_file=PID_FILE,
    )


# ---------- 事件处理（守护进程调用） ----------

def _scan_file(path):
    """对单文件跑 YARA 规则，返回命中规则名列表。"""
    yara_bin = shutil.which("yara")
    if not yara_bin:
        return []
    if not os.path.isdir(RULES_DIR):
        return []
    rule_files = [os.path.join(RULES_DIR, f) for f in os.listdir(RULES_DIR)
                  if f.endswith((".yar", ".yara"))]
    if not rule_files:
        return []
    try:
        r = subprocess.run([yara_bin] + rule_files + [path],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return []
    if r.returncode != 0:
        return []
    return [ln.split()[0] for ln in (r.stdout or "").splitlines() if ln.strip()]


def _quarantine(path):
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    base = os.path.basename(path)
    dest = os.path.join(QUARANTINE_DIR, base)
    i = 1
    while os.path.exists(dest):
        name, ext = os.path.splitext(base)
        dest = os.path.join(QUARANTINE_DIR, f"{name}_{i}{ext}")
        i += 1
    try:
        os.rename(path, dest)
        return dest
    except OSError:
        return None


def _block_in_waf(path):
    """主动防御：为核心 WAF 添加 path_regex 拦截规则（on_change 触发反代 reload）。"""
    try:
        from ...core import waf
        pat = "^" + re.escape(path) + "$"
        waf.add_rule("path_regex", pat, name="cyansec 主动防御")
        return True
    except Exception:
        return False


def _log_event(evt):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(RT_EVENTS, encoding="utf-8") as f:
            events = json.load(f)
    except (OSError, ValueError):
        events = []
    events.append(evt)
    events = events[-500:]
    with open(RT_EVENTS, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def rt_events():
    """实时防护告警记录（最新在前）。"""
    try:
        with open(RT_EVENTS, encoding="utf-8") as f:
            events = json.load(f)
        return list(reversed(events))
    except (OSError, ValueError):
        return []


def _should_scan(path):
    if not os.path.isfile(path):
        return False
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in _SKIP_EXT:
        return False
    if ext and ext not in _SCAN_EXTS:
        return False
    if os.path.abspath(path).startswith(os.path.abspath(QUARANTINE_DIR)):
        return False
    return True


def _handle_event(path):
    """命中处理：扫描 → 告警 → 可选隔离/拦截。"""
    if not _should_scan(path):
        return
    hits = _scan_file(path)
    if not hits:
        return
    conf = _load_conf()
    evt = {"ts": time.time(), "file": path, "rules": hits,
           "quarantined": None, "waf_blocked": False}
    if conf.get("quarantine", True):
        evt["quarantined"] = _quarantine(path)
    if conf.get("waf_block", True):
        evt["waf_blocked"] = _block_in_waf(path)
    _log_event(evt)


# ---------- fanotify 事件循环（内核实时监听） ----------

def _libc():
    name = ctypes.util.find_library("c") or "libc.so.6"
    lib = ctypes.CDLL(name, use_errno=True)
    return lib


def _fanotify_init():
    lib = _libc()
    fn = lib.fanotify_init
    fn.argtypes = [ctypes.c_uint, ctypes.c_uint]
    fn.restype = ctypes.c_int
    return fn(FAN_CLASS_NOTIF | FAN_CLOEXEC, 0)


def _fanotify_mark(fd, mask, path):
    lib = _libc()
    fn = lib.fanotify_mark
    fn.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_uint64,
                   ctypes.c_int, ctypes.c_char_p]
    fn.restype = ctypes.c_int
    return fn(fd, FAN_MARK_ADD | FAN_MARK_MOUNT, mask, -100, path.encode("utf-8"))


def _read_link_fd(fd):
    try:
        return os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return None


def _fanotify_loop(conf, stop):
    """fanotify 阻塞监听。写入/创建/移动事件触发扫描。"""
    fd = _fanotify_init()
    if fd < 0:
        return False  # 不支持 → 调用方回退轮询
    for p in conf.get("paths", []):
        if not os.path.isdir(p):
            continue
        mask = FAN_CLOSE_WRITE | FAN_CREATE | FAN_MOVED_TO | FAN_EVENT_ON_CHILD
        if _fanotify_mark(fd, mask, os.path.abspath(p)) < 0:
            return False
    import select
    while not stop.is_set():
        try:
            r, _, _ = select.select([fd], [], [], 1.0)
        except (OSError, InterruptedError):
            continue
        if not r:
            continue
        while True:
            buf = os.read(fd, _FAN_META()._length_)
            if not buf or len(buf) < _FAN_META()._length_:
                break
            ev_fd = int.from_bytes(buf[_OFF_FD:_OFF_FD + 4], "little")
            if ev_fd >= 0:
                p = _read_link_fd(ev_fd)
                if p:
                    _handle_event(p)
                os.close(ev_fd)
    return True


# ---------- 轮询回退（fanotify 不可用时） ----------

def _poll_loop(conf, stop):
    """轮询扫描配置路径下的可疑扩展名文件（interval 秒）。"""
    interval = conf.get("interval", 5)
    seen = {}
    while not stop.is_set():
        for base in conf.get("paths", []):
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for name in files:
                    p = os.path.join(root, name)
                    ext = os.path.splitext(name)[1].lower().lstrip(".")
                    if ext and ext not in _SCAN_EXTS:
                        continue
                    try:
                        mtime = os.path.getmtime(p)
                    except OSError:
                        continue
                    # 仅处理新出现/变化的文件
                    if seen.get(p) == mtime:
                        continue
                    seen[p] = mtime
                    _handle_event(p)
        time.sleep(interval)


_DAEMON_TEMPLATE = r'''# -*- coding: utf-8 -*-
"""cyansecengine 实时防护守护进程（由插件生成）。"""
import json
import os
import signal
import sys
import threading

sys.path.insert(0, {pkg_root!r})
os.environ.setdefault("AUP_PANEL_HOME", {panel_home!r})
os.environ.setdefault("AUP_CONF_DIR", {conf_dir!r})

CONF_FILE = {conf_file!r}
PID_FILE = {pid_file!r}


def load_conf():
    try:
        with open(CONF_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {{"enabled": False, "paths": []}}


def main():
    conf = load_conf()
    if not conf.get("enabled"):
        sys.exit(0)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: (stop.set(), sys.exit(0)))

    from aups.modules.cyansecengine import rtguard

    try:
        ok = rtguard._fanotify_loop(conf, stop)
    except Exception:
        ok = False
    if not ok:
        rtguard._poll_loop(conf, stop)


if __name__ == "__main__":
    main()
'''
