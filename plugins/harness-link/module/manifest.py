"""harness-link 插件清单：DeepSeek Harness 客户端通信桥。

通过两级令牌授权（配对令牌 -> 会话密钥）让外部 Harness 客户端接入面板，
建立双向消息通道：面板「通信台」下发消息，客户端长轮询取走并回信；
前端按游标增量拉取转录。总览卡片展示在线连接与最近流量。
"""

MANIFEST = {
    "name": "harness-link",
    "title": "Harness 通信桥",
    "version": "0.1.0",
    "description": "与 DeepSeek Harness 客户端建立授权连接：配对令牌接入、双向消息通道、连接管理",
    "type": "external",
    "attr": "功能",
    "config_dir": "harness-link",
    "data_dir": "harness-link",
    "api_module": "aups.modules.harness-link.api",
    "api_paths": [
        "/api/hlink/status",
        "/api/hlink/pairing",
        "/api/hlink/pairing/rotate",
        "/api/hlink/send",
        "/api/hlink/messages",
        "/api/hlink/connections/{conn_id}",
        "/api/hlink/client-script",
        "/api/hlink/connector/register",
        "/api/hlink/connector/heartbeat",
        "/api/hlink/connector/poll",
        "/api/hlink/connector/reply",
    ],
    "frontend_tabs": ["console", "pairing"],
    "entry": [
        {"id": "console", "title": "通信台"},
        {"id": "pairing", "title": "接入授权"},
    ],
    "plugins": [
        {"id": "console", "title": "通信台",
         "description": "查看已连接的 Harness 客户端，双向收发消息（长轮询实时投递）"},
        {"id": "pairing", "title": "接入授权",
         "description": "配对令牌管理、客户端脚本下载、接入指引"},
    ],
}
