"""原生安全组插件清单。"""

MANIFEST = {
    "name": "secgroup",
    "title": "原生安全组",
    "version": "1.1.0",
    "description": "AUPS 原生安全组 provider：使用 nftables 管理端口规则及长亭、CrowdSec、通用 IP 黑名单订阅",
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
        "/api/secgroup/blacklists",
        "/api/secgroup/blacklists/{sub_id}",
        "/api/secgroup/blacklists/sync",
        "/api/secgroup/blacklists/schedule",
    ],
    "cli_groups": ["secgroup"],
    "frontend_tabs": ["secgroup"],
    "modules": ["firewall", "blacklist"],
    "provides": {"firewall": "secgroup"},
    "exports": {
        "python": "aups.modules.secgroup.firewall",
        "api": ["/api/secgroup/status", "/api/secgroup/open", "/api/secgroup/close",
                "/api/secgroup/blacklists", "/api/secgroup/blacklists/sync",
                "/api/secgroup/blacklists/schedule"],
    },
    "entry": [{"id": "overview", "title": "安全组规则"},
              {"id": "blacklists", "title": "黑名单订阅"}],
    "plugins": [
        {"id": "overview", "title": "安全组规则", "description": "nftables 原生端口、协议和来源网段规则"},
        {"id": "blacklists", "title": "黑名单订阅", "description": "订阅长亭 SafeLine、CrowdSec 和通用 IP/CIDR 规则"},
    ],
}
