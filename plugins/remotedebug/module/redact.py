"""输出脱敏：遮蔽凭据类字段，保留校验值与常规日志。

设计取舍：
- 只按「敏感键名」替换其值，不做无差别的高熵串遮蔽——否则会误伤
  update.json 的 apkMd5/apkSha256、versionCode 与版本号，而这些正是排查所需。
- 覆盖 PEM 私钥、Authorization/Bearer、URL userinfo、JSON 与 key=value、
  URL 查询参数等常见泄露形态。
"""

import re

MASK = "***"

# 敏感键名（大小写不敏感）：命中则遮蔽其值
_SECRET_KEY = (r"(?:pass(?:word|wd)?|pwd|secret|token|api[_-]?key|access[_-]?key|"
               r"private[_-]?key|credential|auth|session[_-]?key|signature|salt)")

_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE|OPENSSH PRIVATE KEY)-----.*?"
    r"-----END [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE|OPENSSH PRIVATE KEY)-----",
    re.S)

_AUTH_HEADER = re.compile(r"(?im)^(\s*(?:authorization|proxy-authorization|x-api-key)"
                          r"\s*[:=]\s*).+$")
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{6,}")
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/@\s:]+:[^/@\s]*@")

# "key": "value" / 'key': 'value'（JSON、配置文件）
_QUOTED_KV = re.compile(
    r"([\"'])([A-Za-z0-9_.\-]*" + _SECRET_KEY + r"[A-Za-z0-9_.\-]*)\1"
    r"(\s*:\s*)([\"'])([^\"']*)\4",
    re.I)
# key=value / key: value（shell、env、日志）
_BARE_KV = re.compile(
    r"(^|[\s,{(&?])([A-Za-z0-9_.\-]*" + _SECRET_KEY + r"[A-Za-z0-9_.\-]*)"
    r"(\s*[:=]\s*)([\"']?)([^\s\"'&,;}\]]+)\4",
    re.I | re.M)
# URL 查询参数中的敏感键
_QUERY_KV = re.compile(
    r"([?&][A-Za-z0-9_.\-]*" + _SECRET_KEY + r"[A-Za-z0-9_.\-]*=)([^&\s#\"']*)",
    re.I)


def _sub(text, pattern, repl_for):
    """按 pattern 替换，返回 (新文本, 替换次数)。"""
    count = 0

    def _wrap(m):
        nonlocal count
        count += 1
        return repl_for(m)

    return pattern.sub(_wrap, text), count


def redact_with_count(text, extra_patterns=None):
    """返回 (脱敏文本, 遮蔽次数)。"""
    return _redact(text or "", extra_patterns)


def redact_count(text, extra_patterns=None):
    """返回遮蔽次数（不改动文本），用于面板提示与审计。"""
    return _redact(text or "", extra_patterns)[1]


def redact(text, extra_patterns=None):
    """返回脱敏后的文本。"""
    return _redact(text or "", extra_patterns)[0]


def count(text, extra_patterns=None):
    """redact_count 的简写别名。"""
    return redact_count(text, extra_patterns)


def _redact(text, extra_patterns=None):
    total = 0
    # 顺序有意为之：先整块/整行，再逐值，避免私钥或头值被后续规则切碎后残留。
    text, n = _sub(text, _PEM, lambda m: "[已遮蔽：私钥/证书块]")
    total += n
    text, n = _sub(text, _AUTH_HEADER, lambda m: m.group(1) + MASK)
    total += n
    text, n = _sub(text, _AUTH_SCHEME, lambda m: m.group(1) + " " + MASK)
    total += n
    text, n = _sub(text, _USERINFO, lambda m: m.group(1) + MASK + "@")
    total += n
    text, n = _sub(text, _QUOTED_KV,
                   lambda m: m.group(1) + m.group(2) + m.group(1) + m.group(3)
                   + m.group(4) + MASK + m.group(4))
    total += n
    text, n = _sub(text, _BARE_KV,
                   lambda m: m.group(1) + m.group(2) + m.group(3) + m.group(4)
                   + MASK + m.group(4))
    total += n
    text, n = _sub(text, _QUERY_KV, lambda m: m.group(1) + MASK)
    total += n
    for pattern in extra_patterns or ():
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        text, n = _sub(text, compiled, lambda m: MASK)
        total += n
    return text, total
