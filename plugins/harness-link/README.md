# harness-link — Harness 通信桥

让 DeepSeek Harness 客户端通过授权机制接入 AUPS 面板，建立双向消息通道：
面板「通信台」下发消息 → 客户端长轮询取走并回信 → 面板实时显示回复。

## 授权机制（两级令牌）

1. **配对令牌（pairing token）**：管理员在「接入授权」页查看/轮换。
   客户端用它执行 `register`，换取会话密钥；令牌在轮换前可用于注册多个连接，泄露可随时轮换，不影响已建立连接。
2. **会话密钥（session key）**：`register` 成功后签发，是该连接后续所有通信的凭证。
   管理员可在「接入授权」页吊销连接，密钥立即失效。

令牌比较使用常量时间比较（`hmac.compare_digest`）；配对令牌、会话密钥均为
`secrets.token_urlsafe` 生成；连接数上限 20，单条消息上限 32KB，待投递队列
上限 200 条（超出丢最老）。

## 快速开始

1. 市场安装本插件并启用，打开「Harness 通信桥 → 接入授权」。
2. 复制配对令牌，在 Harness 所在机器下载并运行（脚本零依赖，仅需 Python 3.8+）：
   ```bash
   python harness_link_client.py register \
     --server http://面板地址:端口 --token 配对令牌 --name "我的Harness"
   ```
3. 常驻监听面板消息：
   ```bash
   python harness_link_client.py listen --wait 15
   ```
4. 回复面板：
   ```bash
   python harness_link_client.py send --text "收到"
   ```

register 后凭证保存到 `~/.harness_link.json`，listen/send/status 自动读取。
连接超过心跳窗口（90 秒）判定离线，面板停止向其投递消息；客户端任意轮询/心跳即刷新在线。

## 消息模型

- `out`：面板 → Harness，进入连接待投递队列，客户端长轮询取走（标记已投递）；
- `in`：Harness → 面板，客户端 reply 上行，前端按游标增量拉取；
- 历史追加到 `<data>/transcript.jsonl`（2MB 轮转），消息 id 全局单调递增。

## API 一览

管理面（需面板登录态）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/hlink/status | 状态 + 连接列表（在线/待投递/收发计数） |
| GET | /api/hlink/pairing | 查看配对令牌 |
| POST | /api/hlink/pairing/rotate | 轮换配对令牌 |
| POST | /api/hlink/send | 发送（conn_id 或 * 广播到在线连接） |
| GET | /api/hlink/messages?after=&limit= | 增量拉取转录 |
| DELETE | /api/hlink/connections/{id} | 吊销连接 |
| GET | /api/hlink/client-script | 下载客户端脚本 |

Harness 客户端（Bearer 令牌自认证，不走面板登录）：

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | /api/hlink/connector/register | 配对令牌 | 注册 → 返回 conn_id + session_key |
| POST | /api/hlink/connector/heartbeat | 会话密钥 | 心跳探活 |
| GET | /api/hlink/connector/poll?wait=N | 会话密钥 | 长轮询取待投递消息（N≤25s） |
| POST | /api/hlink/connector/reply | 会话密钥 | 上行回复 |

## 数据与安全

- 配置：`<config>/harness-link/pairing.json`（配对令牌）
- 数据：`<data>/harness-link/state.json`（连接注册表+计数器）、`transcript.jsonl`（消息历史）
- 配对文件、连接状态文件和客户端凭证均按 `0600` 保存；建议经 HTTPS 反代访问面板，HTTP 明文部署时令牌与消息可被链路窃听。
- 面板重启后连接与会话密钥持久保留，客户端无需重新配对；未投递的待发消息也会恢复。
