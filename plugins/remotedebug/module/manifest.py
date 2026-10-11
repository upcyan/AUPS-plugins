"""remotedebug 模块清单：只读远程调试通道（限时令牌 + 有限授权命令）。

定位：让授权方在**不交出面板账户**的前提下，按预设范围查看面板现场信息
（配置、日志、服务状态、配置校验），用于远程排障。

安全边界（逐条对应实现）：
- 只读：命令来自固定目录（runner.CATALOG），不经 shell，无写操作命令；
- 有限：会话可限定 roots（目录）与 commands（命令），TTL 夹在 1 分钟..8 小时；
- 令牌：secrets 随机生成，服务端只存 SHA-256，compare_digest 比较，可即时吊销；
- 脱敏：输出经 redact 遮蔽密码/令牌/私钥等，保留校验值与常规日志；
- 留痕：每次调用写审计（命令、结果、来源 IP、脱敏次数），不记令牌与输出正文。

v0.1.1：修复前端首屏渲染——核心全局 view 是 DOM 元素而非函数，
原写法 view('remotedebug') 抛 TypeError 导致页面停在「正在加载插件」；
改为 document.getElementById('view')，并让 open() 返回 Promise 便于等待渲染。

未实现（框架位，见 api /status 的 interactive 字段）：远程交互式 shell / SSH
会话——需要 PTY 与流式通道，风险面显著更大，本期只保留位置。
"""

MANIFEST = {
    "name": "remotedebug",
    "title": "远程调试",
    "version": "0.1.2",
    "description": "只读远程调试通道：限时随机令牌、预设有限授权命令、目录白名单、输出脱敏与调用审计；用于远程查看面板配置/日志/服务状态排障",
    "type": "external",
    "attr": ["功能", "安全"],
    "deploy": {"host": True},
    "config_dir": "remotedebug",
    "data_dir": "remotedebug",
    "api_module": "aups.modules.remotedebug.api",
    "api_paths": [
        "/api/remotedebug/status",
        "/api/remotedebug/sessions",
        "/api/remotedebug/sessions/{sid}/revoke",
        "/api/remotedebug/revoke-all",
        "/api/remotedebug/audit",
        "/api/remotedebug/catalog",
        "/api/remotedebug/run",
        "/api/remotedebug/exec",
    ],
    "cli_groups": ["remotedebug"],
    "entry": [
        {"id": "terminal", "title": "终端命令"},
    ],
    "plugins": [
        {"id": "terminal", "title": "终端命令",
         "description": "输入只读命令或脚本，输出经脱敏后展示；可开放限时令牌供远程排障"},
    ],
}
