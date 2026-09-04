"""certbot 插件清单：Let's Encrypt 证书签发依赖（属性=依赖）。"""

MANIFEST = {
    "name": "certbot",
    "title": "Certbot",
    "version": "0.3.0",
    "description": "Let's Encrypt 证书签发（certbot）：申请/续期，证书落在面板数据目录。提供 ssl 能力，供核心 Web 正式证书签发",
    "type": "external",
    "attr": "依赖",
    "config_dir": "certbot",
    "data_dir": "certbot",
    "cli_groups": ["certbot"],
    "api_module": "aups.modules.certbot.webapi",
    "api_paths": ["/api/certbot/status", "/api/certbot/install", "/api/certbot/issue"],
    "provides": {"ssl": "certbot"},
    "plugins": [
        {"id": "main", "title": "证书签发", "description": "Certbot 状态/安装/申请证书"},
    ],
}
