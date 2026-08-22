"""caddy 插件：SSL 接入方案（Cloudflare 场景）。

方案 A（flexible）：源站仅 HTTP(80) 服务，TLS 由 Cloudflare 边缘终结；
    全局 auto_https disable_redirects 防重定向循环，站点块显式 http:// 前缀监听 80。
方案 B（dns01）：caddy 通过 Cloudflare API 完成 DNS-01 挑战签发 Let's Encrypt 证书，
    无需公网入站可达；Cloudflare 侧用 Full(strict)。需要带 cloudflare DNS 插件的 caddy 构建。
"""

import os
import json
import shutil

from ... import config
from ...errors import AppError
from . import caddyfile as CF
from . import env as ENV

STATE_FILE = "sslmode.json"


def _state_path():
    return os.path.join(config.plugin_dir("caddy", "config"), STATE_FILE)


def _read_state():
    p = _state_path()
    if not os.path.isfile(p):
        return {"mode": None, "provider": None, "email": "", "domains": [], "token_set": False}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"mode": None, "provider": None, "email": "", "domains": [], "token_set": False}


def _write_state(state):
    p = _state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _binary_supports_dns01():
    """检查当前 caddy 二进制是否包含 cloudflare DNS provider 插件。"""
    b = ENV.caddy_binary()
    if not b:
        return False
    try:
        import subprocess
        res = subprocess.run([b, "list-modules"], capture_output=True, text=True, timeout=10)
        return "dns.providers.cloudflare" in (res.stdout or "").lower()
    except Exception:
        return False


def status():
    """返回当前 SSL 方案状态与诊断信息。"""
    state = _read_state()
    has_dns = _binary_supports_dns01()
    cf = CF.read()
    current_content = cf.get("content", "")
    mode_hint = None
    if "auto_https disable_redirects" in current_content:
        mode_hint = "flexible (auto_https disable_redirects)"
    if "acme_dns cloudflare" in current_content:
        mode_hint = "dns01 (acme_dns cloudflare)"
    # 统计显式 http:// 站点块数量
    http_sites = 0
    for blk in CF._site_blocks(current_content):
        if blk["host"].startswith("http://"):
            http_sites += 1
    return {
        "configured_mode": state.get("mode"),
        "provider": state.get("provider"),
        "email": state.get("email", ""),
        "domains": state.get("domains", []),
        "token_set": state.get("token_set", False),
        "binary_supports_dns01": has_dns,
        "caddyfile_hint": mode_hint,
        "http_sites_count": http_sites,
        "current_caddyfile": current_content,
    }


def apply_flexible(email=""):
    """应用 Flexible 方案：
    1. 全局块确保 auto_https disable_redirects
    2. 为每个现有非 http:// 站点块创建对应的 http:// 孪生块（保留原 body）
    3. 保存并 reload
    """
    state = _read_state()
    state.update({"mode": "flexible", "provider": "cloudflare", "email": email or ""})
    _write_state(state)

    d = CF.read()
    content = d["content"] or ""
    blocks = CF._site_blocks(content)
    if not blocks:
        # 无站点块，仅写入全局选项
        content = CF.ensure_global_options(content)
        CF.write(content)
        return {"ok": True, "message": "已启用 Flexible（无站点块，仅全局配置）", "reloaded": True}

    http_blocks = []
    for blk in blocks:
        host = blk["host"]
        if host.startswith("http://") or host.startswith("https://"):
            continue
        # 生成 http:// 孪生块
        body = blk["body"].strip()
        twin = f"http://{host} {{\n    {body.replace('\n', '\n    ')}\n}}"
        http_blocks.append(twin)

    if not http_blocks:
        CF.write(CF.ensure_global_options(content))
        return {"ok": True, "message": "Flexible 已生效（已有 http:// 孪生块）", "reloaded": True}

    # 在 AUPS APPS SITE 标记区之前/之后插入孪生块
    # 简单：追加到文件末尾，标记为 SSL Flexible 托管区
    begin = "# >>> AUPS SSL FLEXIBLE (managed, do not remove) <<<"
    end = "# <<< AUPS SSL FLEXIBLE >>>"
    section = f"{begin}\n" + "\n\n".join(http_blocks) + f"\n{end}\n"

    # 移除旧的托管区
    content = _remove_section(content, begin, end)
    new_content = (content.rstrip() + "\n\n" + section + "\n") if content.strip() else section + "\n"

    new_content = CF.ensure_global_options(new_content)
    CF.write(new_content)
    return {"ok": True, "message": f"已启用 Flexible，新增 {len(http_blocks)} 个 HTTP 孪生站点", "reloaded": True}


def apply_dns01(email, api_token):
    """应用 DNS-01 方案：
    1. 验证二进制支持 cloudflare DNS provider
    2. 全局块注入 acme_dns cloudflare <token>
    3. 移除 Flexible 的 http:// 孪生块
    4. 保存并 reload
    """
    if not _binary_supports_dns01():
        raise AppError("当前 caddy 二进制不包含 cloudflare DNS provider 插件（dns.providers.cloudflare）。"
                       "请使用 xcaddy 或官方下载页构建带该插件的 caddy，"
                       "然后替换 /opt/aups/runtime/caddy/caddy 并重启。")

    state = _read_state()
    state.update({"mode": "dns01", "provider": "cloudflare", "email": email, "token_set": True})
    _write_state(state)

    d = CF.read()
    content = d["content"] or ""
    # 确保全局块存在，注入 acme_dns
    if not content.strip().startswith("{"):
        content = "{\n}\n" + content
    lines = content.splitlines()
    g = CF._find_global_block_lines(lines)
    if g is None:
        # 无全局块，创建一个
        acme_line = f"    acme_dns cloudflare {api_token}"
        content = "{\n" + acme_line + "\n}\n" + content
    else:
        # 插入/更新 acme_dns 行
        acme_line = f"    acme_dns cloudflare {api_token}"
        # 先移除已有的 acme_dns 行
        new_lines = []
        for ln in lines:
            if ln.strip().startswith("acme_dns"):
                continue
            new_lines.append(ln)
        # 在全局块内插入
        new_lines.insert(g[0] + 1, acme_line)
        content = "\n".join(new_lines)

    # 移除 Flexible 托管的 http:// 孪生块区
    begin = "# >>> AUPS SSL FLEXIBLE (managed, do not remove) <<<"
    end = "# <<< AUPS SSL FLEXIBLE >>>"
    content = _remove_section(content, begin, end)

    CF.write(content)
    return {"ok": True, "message": "已启用 DNS-01，证书将通过 Cloudflare API 自动签发", "reloaded": True}


def disable_ssl_mode():
    """禁用 SSL 特殊方案：移除托管区，恢复默认自动 HTTPS。"""
    state = _read_state()
    state.update({"mode": None, "provider": None, "email": "", "domains": [], "token_set": False})
    _write_state(state)

    d = CF.read()
    content = d["content"] or ""
    # 移除 Flexible 托管区
    begin = "# >>> AUPS SSL FLEXIBLE (managed, do not remove) <<<"
    end = "# <<< AUPS SSL FLEXIBLE >>>"
    content = _remove_section(content, begin, end)
    # 移除 DNS-01 的 acme_dns 行
    lines = content.splitlines()
    new_lines = [ln for ln in lines if not ln.strip().startswith("acme_dns")]
    content = "\n".join(new_lines)
    # 移除全局块中的 auto_https disable_redirects（若无其他行则可保留，write 会重新校验）
    CF.write(content)
    return {"ok": True, "message": "已恢复默认自动 HTTPS 行为"}


def _remove_section(text, begin, end):
    """移除所有标记区（含旧版错误产生的嵌套标记）。"""
    lines = text.splitlines()
    result = []
    depth = 0
    for line in lines:
        if begin in line:
            depth += 1
            continue
        if end in line:
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            result.append(line)
    return "\n".join(result)


def download_caddy_with_cloudflare():
    """下载带 cloudflare DNS 插件的 caddy（通过 caddy 官方 API 构建）。
    返回下载的二进制路径，调用者需替换现有 caddy 并重启。
    """
    import urllib.request
    import tempfile
    url = "https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com%2Fcaddy-dns%2Fcloudflare"
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
        tmp.close()
        urllib.request.urlretrieve(url, tmp.name)
        # 解压
        import tarfile
        extract_dir = tempfile.mkdtemp()
        with tarfile.open(tmp.name, "r:gz") as tf:
            tf.extractall(extract_dir)
        # 找到 caddy 二进制
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f == "caddy":
                    bin_path = os.path.join(root, f)
                    shutil.chmod(bin_path, 0o755)
                    return bin_path
        raise AppError("解压后未找到 caddy 二进制")
    except Exception as e:
        raise AppError(f"下载构建失败: {e}")