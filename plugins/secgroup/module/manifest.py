"""原生安全组插件清单。"""

MANIFEST = {
    "name": "secgroup",
    "title": "原生安全组",
    "version": "1.0.0",
    "description": "AUPS 原生安全组 provider：使用 nftables 专用链按端口、协议和来源网段管理访问，不依赖 ufw/firewalld，不改写系统已有规则",
    "type": "external",
    "attr": "依赖",
    "deploy": {"host": True},
    "config_dir": "secgroup",
    "data_dir": "secgroup",
    "api_module": "aups.modules.secgroup.api",
    "api_paths": [
        "/api/secgroup/status",
        "/api/secgroup/open",
        "/api/secgroup/close",
    ],
    "frontend_tabs": ["secgroup"],
    "modules": ["firewall"],
    "provides": {"firewall": "secgroup"},
    "exports": {
        "python": "aups.modules.secgroup.firewall",
        "api": ["/api/secgroup/status", "/api/secgroup/open", "/api/secgroup/close"],
    },
    "entry": [{"id": "overview", "title": "安全组规则"}],
    "plugins": [{
        "id": "overview", "title": "安全组规则",
        "description": "nftables 原生端口、协议和来源网段规则",
    }],
}
