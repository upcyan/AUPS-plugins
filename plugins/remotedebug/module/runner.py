"""只读命令执行：固定 argv、白名单二进制与旗标、根目录约束、输出脱敏。

安全边界（每条都对应一个真实可利用面）：
- 绝不经过 shell：shell 元字符在引号外一律拒绝，故 ``|``/``;``/``&&``/``>``
  与反引号、``$(...)`` 都无法生效；``grep -E "a|b"`` 引号内的 ``|`` 仍放行。
- 二进制只从固定目录解析，不读 PATH，避免前置目录投放同名程序（PATH 劫持）。
- 只允许目录中的二进制；``rm``/``curl``/``sh``/``python`` 等一律不在目录内。
- 旗标白名单：``find -delete``、``tail -f``、``caddy fmt --overwrite``、
  ``ls -Z`` 等写入或挂起用法会被拒绝。
- 非旗标参数按路径校验：含 ``/``、或在工作目录下真实存在（含符号链接）的
  参数，其 realpath 必须位于允许根目录内，因此 ``../`` 穿越与符号链接逃逸
  都会失败。
- 脚本整体先校验后执行：任一行不安全则整批拒绝，不产生半执行状态。
"""

import os
import shutil
import subprocess
import time

from ...errors import AppError
from . import redact as R

# 固定解析目录（不含 PATH，避免劫持）。面板自带的运行时二进制（如
# /opt/aups/runtime/caddy/caddy）不在系统目录，因此额外加入面板 runtime 根，
# 命名规则为 runtime/<插件>/<命令>（见 config.plugin_dir 约定）。
_FIXED_BIN_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin",
                   "/usr/local/sbin")


def _panel_runtime_dirs():
    """面板插件运行时目录（仅返回存在的），使面板自带二进制可被解析。"""
    base = os.path.join(os.environ.get("AUP_PANEL_HOME", "/opt/aups"), "runtime")
    try:
        return [os.path.join(base, d) for d in sorted(os.listdir(base))
                if os.path.isdir(os.path.join(base, d))]
    except OSError:
        return []

# shell 元字符：引号外出现即拒绝
_METACHARS = set(";|&<>`$(){}[]*?!~")

MAX_STEPS = 8
MAX_TIMEOUT = 30
MAX_OUTPUT = 64 * 1024
_TRUNCATE_MARK = "\n…[输出已截断]"

# 只读命令目录。flags 为允许的旗标白名单（含 -= 形式需原样列出）；
# subcommands 非空时，第一个非旗标参数必须是其中之一。
CATALOG = {
    "cat": {"description": "查看文件内容", "flags": set()},
    "ls": {"description": "列目录", "flags": {"-a", "-l", "-h", "-la", "-al", "-lh",
                                              "-hl", "-R", "-t", "-r", "-1",
                                              "--all", "--long", "--human-readable"}},
    "head": {"description": "查看文件开头", "flags": {"-n", "--lines", "-c", "--bytes",
                                                      "-q", "-v"}},
    "tail": {"description": "查看文件结尾（不支持 -f 跟随）",
             "flags": {"-n", "--lines", "-c", "--bytes", "-q", "-v"}},
    "grep": {"description": "按模式检索（不支持写入类旗标）",
             "flags": {"-E", "-e", "-i", "-n", "-r", "-R", "-l", "-c", "-v", "-w",
                       "-x", "-F", "-A", "-B", "-C", "-H", "-h", "-s",
                       "--line-number", "--recursive", "--ignore-case",
                       "--count", "--fixed-strings", "--extended-regexp",
                       "--no-messages", "--with-filename", "--no-filename"}},
    "find": {"description": "查找文件（不支持 -delete/-exec）",
             "flags": {"-name", "-iname", "-type", "-maxdepth", "-mindepth", "-path",
                       "-not", "-print", "-newer", "-size", "-mtime", "-perm",
                       "-user", "-group", "-a", "-o"}},
    "stat": {"description": "文件元信息", "flags": {"-c", "--format", "-L"}},
    "file": {"description": "识别文件类型", "flags": {"-b", "--brief", "-i", "--mime"}},
    "wc": {"description": "统计行/字/字节", "flags": {"-l", "-c", "-w", "-m"}},
    "du": {"description": "目录占用", "flags": {"-s", "-h", "-a", "--max-depth", "-c"}},
    "df": {"description": "磁盘空间", "flags": {"-h", "-T", "-i", "-a"}},
    "id": {"description": "当前身份", "flags": set()},
    "uname": {"description": "内核信息", "flags": {"-a", "-r", "-s", "-m"}},
    "date": {"description": "当前时间", "flags": {"-I", "-Is", "-u", "-R"}},
    "ps": {"description": "进程列表", "flags": {"-e", "-f", "-ef", "-a", "-u", "-x",
                                                "-aux", "-o", "--sort"}},
    "ss": {"description": "套接字/监听端口",
           "flags": {"-t", "-l", "-n", "-p", "-a", "-u", "-x", "-e", "-4", "-6",
                     "-s", "-ltnp", "-tlnp", "-tln"}},
    "systemctl": {"description": "服务状态（只读子命令）",
                  "flags": {"--no-pager", "--plain", "-l", "--full", "--all", "--type"},
                  "subcommands": {"status", "show", "is-active", "is-enabled",
                                  "is-failed", "list-units", "list-unit-files",
                                  "cat", "list-timers", "list-sockets"}},
    "journalctl": {"description": "系统日志（只读）",
                   "flags": {"-u", "--unit", "-n", "--lines", "--no-pager", "-p",
                             "--priority", "--since", "--until", "-b", "--boot",
                             "-o", "--output", "--disk-usage", "-k", "--no-hostname",
                             "-g", "--grep"},
                   "subcommands": set()},
    "caddy": {"description": "Caddy 配置校验/适配（不支持 fmt --overwrite）",
              "flags": {"--config", "--adapter", "--pretty", "--resume", "-c"},
              "subcommands": {"validate", "adapt", "version", "list-modules",
                              "environ", "fmt", "storage"}},
    "docker": {"description": "容器只读查询",
               "flags": {"-a", "--all", "-f", "--filter", "--format", "-n", "--tail",
                         "--no-trunc", "-q", "--quiet"},
               "subcommands": {"ps", "images", "inspect", "logs", "version", "info",
                               "port", "stats"}},
}


def catalog():
    """返回命令目录（供面板展示可选命令）。"""
    return {name: {"description": spec["description"],
                   "flags": sorted(spec["flags"]),
                   "subcommands": sorted(spec.get("subcommands") or ()),
                   "read_only": True}
            for name, spec in CATALOG.items()}


def _reject_unquoted_metachars(line):
    """引号外的 shell 元字符一律拒绝，并拒绝换行注入。"""
    quote = None
    escaped = False
    for ch in line:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            continue
        if ch in _METACHARS:
            raise AppError(f"命令包含不允许的 shell 字符：{ch!r}（只支持单条只读命令）")
    if quote:
        raise AppError("命令引号未闭合")


def _resolve_bin(name):
    """从固定目录与面板运行时目录解析二进制；不使用 PATH，防同名劫持。"""
    if "/" in name:
        raise AppError("命令必须使用名称（不接受自定义路径）")
    for directory in [d for d in _FIXED_BIN_DIRS if os.path.isdir(d)] + _panel_runtime_dirs():
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.realpath(candidate)
    raise AppError(f"未找到可用的命令：{name}（面板自带工具或系统只读工具）")


def _inside(path, roots):
    """realpath 后必须位于某个允许根目录内。"""
    real = os.path.realpath(path)
    for root in roots:
        base = os.path.realpath(root)
        if real == base or real.startswith(base + os.sep):
            return True
    return False


def _check_token_path(token, cwd, roots):
    """非旗标参数若指向真实路径（含符号链接），必须落在允许根内。"""
    if ".." in token.split("/"):
        raise AppError(f"路径不允许包含 ..：{token}")
    candidate = token if os.path.isabs(token) else os.path.join(cwd, token)
    looks_like_path = "/" in token or os.path.lexists(candidate)
    if not looks_like_path:
        return
    if not _inside(candidate, roots):
        raise AppError(f"路径超出允许范围：{token}")


def validate_line(line, roots, cwd=None, allowed_bins=None):
    """校验单条命令，返回执行计划 {bin, argv, cwd}；不安全则抛错。

    allowed_bins 非空时，命令名须在其中（会话级范围限制）。
    """
    import shlex

    line = (line or "").strip()
    if not line:
        raise AppError("命令为空")
    if "\n" in line or "\r" in line:
        raise AppError("单条命令不得包含换行")
    _reject_unquoted_metachars(line)
    try:
        tokens = shlex.split(line)
    except ValueError as e:
        raise AppError(f"命令解析失败：{e}")
    if not tokens:
        raise AppError("命令为空")

    name = tokens[0]
    spec = CATALOG.get(name)
    if spec is None:
        raise AppError(f"命令不在只读目录中：{name}"
                       "（仅允许：" + "、".join(sorted(CATALOG)) + "）")
    if allowed_bins and name not in allowed_bins:
        raise AppError(f"本次授权未开放该命令：{name}")

    root_list = [str(r) for r in (roots or [])]
    if not root_list:
        raise AppError("未配置允许访问的目录")

    cwd = cwd or root_list[0]
    if not _inside(cwd, root_list):
        raise AppError("工作目录超出允许范围")

    subcommands = spec.get("subcommands") or set()
    first_arg = None
    for token in tokens[1:]:
        if token.startswith("-"):
            if token not in spec["flags"]:
                raise AppError(f"命令 {name} 不允许使用旗标：{token}")
            continue
        if first_arg is None:
            first_arg = token
            if subcommands:
                if token not in subcommands:
                    raise AppError(
                        f"命令 {name} 不支持子命令：{token}"
                        "（仅允许：" + "、".join(sorted(subcommands)) + "）")
                continue
        _check_token_path(token, cwd, root_list)

    return {"bin": _resolve_bin(name), "argv": [name] + tokens[1:], "cwd": cwd,
            "name": name}


def _run_plan(plan, timeout, max_output):
    started = time.monotonic()
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C",
           "HOME": "/nonexistent"}
    try:
        proc = subprocess.run([plan["bin"]] + plan["argv"][1:], cwd=plan["cwd"],
                              env=env, shell=False, capture_output=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AppError(f"命令执行超时（>{timeout}s）：{plan['name']}")
    except OSError as e:
        raise AppError(f"命令执行失败：{e}")
    duration = int((time.monotonic() - started) * 1000)

    out, err = proc.stdout, proc.stderr
    truncated = len(out) > max_output
    if truncated:
        out = out[:max_output]
    text_out = out.decode("utf-8", "replace")
    text_err = err.decode("utf-8", "replace")
    if truncated:
        text_out += _TRUNCATE_MARK
    clean_out, n_out = R._redact(text_out)
    clean_err, n_err = R._redact(text_err)
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "stdout": clean_out, "stderr": clean_err, "truncated": truncated,
            "redactions": n_out + n_err, "duration_ms": duration,
            "output_bytes": len(out), "command": plan["name"],
            "argv": plan["argv"]}


def _positive_int(value, name, minimum, maximum, allow_none=False, default=None):
    """把客户端可控数值参数解析为受限整数；非法一律 AppError（干净 400）。

    这些参数来自请求体，绝不能直接参与比较或运算：字符串/None 会抛
    TypeError，越界值不能静默夹紧（会让调用方误以为生效）。
    """
    if value is None or value == "":
        if allow_none:
            return default
        raise AppError(f"{name} 需为 {minimum}-{maximum} 的整数")
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str):
            try:
                value = int(value.strip())
            except ValueError:
                raise AppError(f"{name} 需为 {minimum}-{maximum} 的整数：{value!r}")
        else:
            raise AppError(f"{name} 需为 {minimum}-{maximum} 的整数")
    if value < minimum or value > maximum:
        raise AppError(f"{name} 需为 {minimum}-{maximum} 的整数：{value}")
    return value


def execute(text, roots, cwd=None, max_steps=MAX_STEPS, timeout=10,
            max_output=MAX_OUTPUT, allowed_bins=None):
    """执行单条命令或多行只读脚本（整批先校验后执行）。"""
    limit = _positive_int(max_steps, "max_steps", 1, MAX_STEPS,
                          allow_none=True, default=MAX_STEPS)
    timeout = _positive_int(timeout, "timeout", 1, MAX_TIMEOUT,
                            allow_none=True, default=10)
    max_output = _positive_int(max_output, "max_output", 1, MAX_OUTPUT,
                               allow_none=True, default=MAX_OUTPUT)
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not lines:
        raise AppError("命令为空")
    if len(lines) > limit:
        raise AppError(f"单次最多执行 {limit} 条命令（当前 {len(lines)} 条）")

    plans = [validate_line(l, roots=roots, cwd=cwd, allowed_bins=allowed_bins)
             for l in lines]  # 任一行不安全 → 整批抛错，不产生半执行
    steps = [_run_plan(p, timeout, max_output) for p in plans]

    ok = all(s["ok"] for s in steps)
    result = {"ok": ok, "steps": steps,
              "redactions": sum(s["redactions"] for s in steps),
              "truncated": any(s["truncated"] for s in steps),
              "duration_ms": sum(s["duration_ms"] for s in steps)}
    if len(steps) == 1:
        result.update({k: steps[0][k] for k in
                       ("stdout", "stderr", "exit_code", "command", "argv")})
    else:
        result.update({"stdout": "\n".join(s["stdout"] for s in steps),
                       "stderr": "\n".join(s["stderr"] for s in steps),
                       "exit_code": 0 if ok else next(
                           s["exit_code"] for s in steps if not s["ok"])})
    return result


def which(name):
    """判断命令是否可用（供面板展示）。"""
    try:
        return _resolve_bin(name)
    except AppError:
        return None


def environment():
    """运行环境摘要（只读，供面板显示）。"""
    return {"platform": os.uname().sysname if hasattr(os, "uname") else "",
            "available": sorted(n for n in CATALOG if which(n)),
            "missing": sorted(n for n in CATALOG if not which(n)),
            "max_steps": MAX_STEPS, "max_timeout": MAX_TIMEOUT,
            "max_output": MAX_OUTPUT}
