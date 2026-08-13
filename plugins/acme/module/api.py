"""acme.sh 业务逻辑（CLI / Web 共用）。

acme.sh 脚本统一部署到 PANEL_HOME/runtime/acme（--installhome），
其 home/证书/配置落在 PANEL_HOME/data/acme（--home），便于卸载清理与备份。
"""

import os

from ... import config
from ...errors import AppError
from ...util import has_cmd, run


def _acme_bin():
    return os.path.join(config.plugin_dir("acme", "runtime"), "acme.sh")


def status():
    d = config.plugin_paths("acme")
    bin_path = _acme_bin()
    installed = os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)
    ver = None
    if installed:
        r = run([bin_path, "--version"])
        ver = (r.stdout or r.stderr or "").strip()
    return {"name": "acme", "installed": installed, "version": ver,
            "bin": bin_path,
            "runtime_dir": d["runtime"], "config_dir": d["config"], "data_dir": d["data"]}


def install():
    """部署 acme.sh 到 PANEL_HOME/runtime/acme，home 指向 PANEL_HOME/data/acme。"""
    bin_path = _acme_bin()
    if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
        return {"ok": True, "source": "runtime", "message": "acme.sh 已安装", **status()}
    config.ensure_panel_dirs("acme")
    runtime = config.plugin_dir("acme", "runtime")
    data = config.plugin_dir("acme", "data")
    if not has_cmd("git"):
        raise AppError("未找到 git，请先安装 git（apt-get install -y git）")
    if not os.path.isdir(os.path.join(runtime, ".git")):
        run(["git", "clone", "--depth", "1",
             "https://github.com/acmesh-official/acme.sh.git", runtime], check=True)
    if not (os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)):
        raise AppError("acme.sh 部署失败，未找到可执行脚本: " + bin_path)
    # 默认 CA 设为 Let's Encrypt（避免 ZeroSSL 需邮箱注册）
    run([bin_path, "--set-default-ca", "--server", "letsencrypt", "--home", data], check=True)
    return {"ok": True, "source": "runtime", "message": "acme.sh 已部署到面板目录", **status()}


def _setup_renew():
    """写入自动续期 cron（acme.sh --cron 按到期自动续）。"""
    bin_path = _acme_bin()
    data = config.plugin_dir("acme", "data")
    cron = "/etc/cron.d/aups-acme-renew"
    try:
        with open(cron, "w") as f:
            f.write(f"0 3 * * * root {bin_path} --cron --home {data} >/dev/null 2>&1\n")
        os.chmod(cron, 0o600)
    except OSError as e:
        print(f"[警告] 无法设置自动续期: {e}")


def request_cert(domain, email=None):
    """用 acme.sh 申请证书（standalone 验证），home 落在 PANEL_HOME/data/acme。"""
    domain = (domain or "").strip().lower()
    if not domain:
        raise AppError("请提供域名")
    bin_path = _acme_bin()
    if not (os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)):
        raise AppError("未检测到 acme.sh，请先执行 install")
    data = config.plugin_dir("acme", "data")
    os.makedirs(data, exist_ok=True)
    cmd = [bin_path, "--issue", "-d", domain, "--standalone", "--httpport", "80",
           "--home", data]
    if email:
        cmd += ["--accountemail", email]
    run(cmd, check=True)
    cert = os.path.join(data, domain, "fullchain.cer")
    key = os.path.join(data, domain, f"{domain}.key")
    if not (os.path.isfile(cert) and os.path.isfile(key)):
        raise AppError("证书申请完成，但未找到证书文件: " + os.path.join(data, domain))
    _setup_renew()
    return {"ok": True, "domain": domain, "cert": cert, "key": key, "data_dir": data}


def renew():
    """续期：acme.sh --renew-all，home 同申请时。"""
    bin_path = _acme_bin()
    if not (os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)):
        raise AppError("未检测到 acme.sh，请先执行 install")
    data = config.plugin_dir("acme", "data")
    run([bin_path, "--renew-all", "--home", data], check=True)
    return {"ok": True, "message": "续期完成", "data_dir": data}
