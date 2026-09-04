"""certbot 业务逻辑（CLI / Web 共用）。

certbot 部署的证书/配置/日志统一落在 PANEL_HOME/data/certbot（--config-dir/--work-dir/--logs-dir），
便于卸载清理与备份；软件本体复用系统 certbot 或 apt 安装。
"""

import os
import shutil

from ... import config
from ... import pkg
from ...errors import AppError
from ...util import has_cmd, run


def status():
    d = config.plugin_paths("certbot")
    ver = None
    if has_cmd("certbot"):
        r = run(["certbot", "--version"])
        ver = (r.stdout or r.stderr or "").strip()
    return {"name": "certbot", "installed": has_cmd("certbot"), "version": ver,
            "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}


def find_cert(domain=None):
    """查找本插件数据目录下的证书。返回 (cert, key) 或 (None, None)。

    certbot 证书落在 `data/certbot/live/<domain>/fullchain.pem`。
    核心 SSL 抽象层（aups.core.ssl）在签发前用它做去重，避免重复申请。
    """
    data = config.plugin_dir("certbot", "data")
    candidates = []
    if domain:
        candidates.append(os.path.join(data, "live", (domain or "").strip().lower(), "fullchain.pem"))
    else:
        live = os.path.join(data, "live")
        if os.path.isdir(live):
            for d in sorted(os.listdir(live)):
                candidates.append(os.path.join(live, d, "fullchain.pem"))
    for cert in candidates:
        key = cert.replace("fullchain.pem", "privkey.pem")
        if os.path.isfile(cert) and os.path.isfile(key):
            return cert, key
    return None, None


def install():
    """安装 certbot：优先复用系统，否则用包管理器安装（跨发行版，含发行版别名）。"""
    if has_cmd("certbot"):
        return {"ok": True, "source": "system", "message": "已检测到系统 certbot，直接使用",
                **status()}
    config.ensure_panel_dirs("certbot")
    pkg.install(["certbot", "python3-certbot"])
    if not has_cmd("certbot"):
        raise AppError("certbot 安装后仍未检测到，请检查安装日志")
    return {"ok": True, "source": "pkg", "message": "已通过包管理器安装 certbot", **status()}


def _renew_cron_line():
    bin_path = shutil.which("certbot") or "certbot"
    data = config.plugin_dir("certbot", "data")
    return (f"0 3 * * * root {bin_path} renew --quiet "
            f"--config-dir {data} --work-dir {data} --logs-dir {data} >/dev/null 2>&1\n")


def _setup_renew():
    """写入自动续期 cron（指向面板数据目录，而非系统默认 /etc/letsencrypt）。"""
    cron = "/etc/cron.d/aups-certbot-renew"
    try:
        with open(cron, "w") as f:
            f.write(_renew_cron_line())
        os.chmod(cron, 0o600)
    except OSError as e:
        print(f"[警告] 无法设置自动续期: {e}")


def request_cert(domain, email=None):
    """用 certbot 申请证书（standalone 验证，80 端口占用时回退 webroot），证书落在数据目录。"""
    domain = (domain or "").strip().lower()
    if not domain:
        raise AppError("请提供域名")
    if not has_cmd("certbot"):
        raise AppError("未检测到 certbot，请先执行 install")
    config.ensure_panel_dirs("certbot")
    data = config.plugin_dir("certbot", "data")
    base = ["certbot", "certonly", "--non-interactive", "--agree-tos", "--no-eff-email",
            "--config-dir", data, "--work-dir", data, "--logs-dir", data, "-d", domain]
    email_args = ["-m", email] if email else ["--register-unsafely-without-email"]
    res = run(base + ["--standalone"] + email_args)
    if res.returncode != 0:
        res = run(base + ["--webroot", "-w", config.BASE_DIR] + email_args, check=True)
    cert = os.path.join(data, "live", domain, "fullchain.pem")
    key = os.path.join(data, "live", domain, "privkey.pem")
    if not (os.path.isfile(cert) and os.path.isfile(key)):
        raise AppError("证书申请完成，但未找到证书文件: " + os.path.join(data, "live", domain))
    _setup_renew()
    return {"ok": True, "domain": domain, "cert": cert, "key": key, "data_dir": data}


def renew():
    """续期：certbot renew，配置目录同申请时。"""
    if not has_cmd("certbot"):
        raise AppError("未检测到 certbot，请先执行 install")
    data = config.plugin_dir("certbot", "data")
    run(["certbot", "renew", "--config-dir", data, "--work-dir", data,
         "--logs-dir", data], check=True)
    return {"ok": True, "message": "续期完成", "data_dir": data}


def list_certs():
    data = config.plugin_dir("certbot", "data")
    live = os.path.join(data, "live")
    out = []
    for domain in sorted(os.listdir(live)) if os.path.isdir(live) else []:
        cert, key = os.path.join(live, domain, "fullchain.pem"), os.path.join(live, domain, "privkey.pem")
        if os.path.isfile(cert) and os.path.isfile(key): out.append({"domain": domain, "cert": cert, "key": key, "provider": "certbot"})
    return out


def delete_cert(domain):
    domain = (domain or "").strip().lower()
    if not domain or "/" in domain or ".." in domain: raise AppError("域名无效")
    data = config.plugin_dir("certbot", "data")
    run(["certbot", "delete", "--non-interactive", "--cert-name", domain, "--config-dir", data, "--work-dir", data, "--logs-dir", data], check=True)
    return {"ok": True, "domain": domain, "deleted": True}


def remove():
    """卸载：删除续期 cron（保留 config/data 证书/配置，由市场 keep_data 决定）。"""
    for cron in ("/etc/cron.d/aups-certbot-renew",):
        try:
            os.remove(cron)
        except OSError:
            pass
    return {"name": "certbot", "removed": True}
