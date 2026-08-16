"""acme 插件清单：acme.sh 证书签发依赖（属性=依赖）。"""

MANIFEST = {
    "name": "acme",
    "title": "acme.sh",
    "version": "0.2.0",
    "description": "acme.sh 证书签发（零依赖脚本）：申请/续期，脚本与证书落在面板目录。提供 ssl 能力，供核心 Web 正式证书签发",
    "type": "external",
    "attr": "依赖",
    "config_dir": "acme",
    "data_dir": "acme",
    "cli_groups": ["acme"],
    "api_module": "aups.modules.acme.webapi",
    "api_paths": ["/api/acme/status", "/api/acme/install", "/api/acme/issue"],
    "provides": {"ssl": "acme"},
    "plugins": [
        {"id": "main", "title": "证书签发", "description": "acme.sh 状态/安装/申请证书"},
    ],
}
