# 服务端客户端连接监控后端实施计划

> 编制日期：2026-08-23
> 状态：待实施
> 对应前端设计：`.pen/server-monitor.pen`

## 1. 目标

为具备“客户端连接”语义的网络服务端统一增加连接监控能力，向前端稳定提供：

- 当前连接：客户端 IP/端口、连接建立时间、实时连接时长、最近活动时间、连接状态等。
- 历史连接：断开时间、总连接时长、断开原因、流量/报文统计等。
- 服务概览：服务是否运行、当前连接数、今日连接/断开次数、异常断开数等。
- 每个设备（`channel_id`）保留最近 100 条已结束连接，数量可通过配置覆盖，但默认值和产品行为固定为 100。

该能力只描述客户端会话，不改变现有协议业务处理流程，也不把“服务端已启动”误报为“已有客户端连接”。

## 2. 范围与边界

### 2.1 本期纳入

| 协议服务端 | 连接语义 | 本期监测 |
| --- | --- | --- |
| Modbus TCP / RTU over TCP | TCP 会话，可多客户端 | 是 |
| IEC 60870-5-104 | TCP/TLS 会话，可多客户端 | 是 |
| DL/T 645 TCP | TCP 会话 | 是 |
| IEC 61850 MMS | TCP 会话，可多客户端 | 是 |
| DNP3 TCP Server | TCP 会话，当前实现为单活动连接 | 是 |

### 2.2 明确排除

- Modbus UDP：无连接概念，本功能不采集、不展示最近访问端点。
- IEC 61850 GOOSE：组播发布/订阅，已有独立监测，本功能不重复建设。
- Modbus RTU、DL/T 645 串口等串行链路：没有客户端 IP，不进入网络客户端连接列表。
- 主站/客户端模式设备：本功能只面向服务端角色。

后端必须通过能力判断返回“不支持”，不能为排除项构造伪连接。

## 3. 核心设计决策

1. **运行状态与连接状态分离。** `device.is_protocol_running()` 继续表示服务是否启动；新增连接摘要表示是否有客户端在线。
2. **统一模型、协议适配。** 各协议只上报标准化生命周期事件，公共模块负责状态、计时、并发、持久化和保留策略。
3. **当前连接以内存为准。** 查询高频、持续时间实时变化，不为每次轮询写数据库。
4. **历史连接以数据库为准。** 断开后异步落库，每个 `channel_id` 只保留最新 100 条完整记录。
5. **协议回调不直接写数据库。** 原生库回调可能来自 asyncio、线程或 C 回调线程，回调路径必须短、可重入、无阻塞。
6. **单调时钟负责运行中计时。** 展示时间使用 UTC 时间戳，连接时长使用 `time.monotonic_ns()` 计算，避免系统校时导致负时长。
7. **生命周期事件幂等。** 重复断开、服务停止与网络异常同时发生时，一条连接只能结束一次。

## 4. 总体架构

```text
协议库连接回调
    │ connect / activity / disconnect
    ▼
协议适配器（仅提取连接句柄、端点、身份、原因）
    ▼
ConnectionSessionRegistry（线程安全、统一状态机）
    ├── 当前连接不可变快照 ──► API 查询
    └── 有界事件队列 ─────────► 后台持久化器
                                  ├── connection_session 历史表
                                  └── 每设备保留最近 100 条
```

建议新增公共模块：

```text
src/device/core/connection/
├── __init__.py
├── models.py          # 会话、端点、摘要、枚举、不可变 DTO
├── registry.py        # 生命周期状态机、当前连接索引、统计快照
└── persistence.py     # 有界队列、后台批量写入、保留和恢复

src/data/model/
└── connection_session.py

src/web/api/schemas/
└── connection.py

src/web/api/device/
└── connection_router.py  # 或并入现有 device/router.py
```

`ServerHandler` 增加只读连接监控能力，设备层不感知具体协议的连接句柄：

```python
class ServerHandler(ProtocolHandler):
    def supports_connection_monitoring(self) -> bool: ...
    def get_connection_summary(self) -> ConnectionSummary: ...
    def list_current_connections(self) -> tuple[ConnectionSnapshot, ...]: ...
```

连接历史由公共查询服务读取数据库，不要求每个协议分别实现。

## 5. 统一会话模型

### 5.1 必备字段

| 字段 | 含义 |
| --- | --- |
| `session_id` | ULID/UUID，会话全局唯一标识 |
| `channel_id` | 设备/通道主键，历史保留策略的隔离键 |
| `protocol_type` | 规范化协议类型，如 `modbus_tcp`、`iec104` |
| `server_instance_id` | 单次服务启动实例 ID，用于区分重启前后的会话 |
| `remote_ip` / `remote_port` | 客户端端点，兼容 IPv4/IPv6 |
| `local_ip` / `local_port` | 本地监听端点 |
| `state` | 当前统一状态 |
| `transport_connected_at` | TCP 接入时间，UTC |
| `established_at` | 协议会话建立时间；无法区分时与 TCP 接入时间相同 |
| `last_activity_at` | 最近收到或发送有效数据的时间 |
| `disconnected_at` | 已确认断开的时间；异常恢复无法确定时可为空 |
| `duration_ms` | 已结束连接的最终时长 |
| `disconnect_reason` | 规范化断开原因 |
| `disconnect_initiator` | `remote`、`server`、`network`、`process`、`unknown` |

### 5.2 建议补充字段

- `client_identity`：协议可识别的站地址、公共地址、IED 客户端信息等 JSON；不得把凭证和密钥写入记录。
- `security`：是否 TLS、协商协议、证书指纹/主题摘要等脱敏信息。
- `rx_bytes`、`tx_bytes`、`rx_messages`、`tx_messages`、`error_count`：诊断连接质量。
- `close_detail`：受长度限制的技术详情，只记录可展示的错误摘要，禁止写堆栈、报文正文或秘密信息。
- `end_time_accuracy`：`exact` 或 `estimated`，用于进程异常退出后的历史展示。

运行中的 `duration_ms` 不存为不断更新的值，由 `now_monotonic - connected_monotonic` 实时计算。

### 5.3 状态机

```text
CONNECTING → ESTABLISHED → ACTIVE ↔ IDLE → CLOSED
       └───────────────异常──────────────→ ABNORMAL
```

- `ESTABLISHED`：传输或协议握手完成。
- `ACTIVE`：近期有业务活动。
- `IDLE`：连接仍在线，但超过协议配置的活动阈值。
- `CLOSED`：正常结束，进入历史记录。
- `ABNORMAL`：异常结束，进入历史记录；不是“当前连接”状态。

第一期前端若只需要“在线/空闲”，API 仍返回完整规范状态，前端可映射显示。

### 5.4 断开原因枚举

至少支持：

- `remote_closed`
- `network_reset`
- `idle_timeout`
- `protocol_error`
- `tls_handshake_failed`
- `authentication_failed`
- `server_stopped`
- `connection_replaced`
- `max_connections_rejected`
- `process_terminated`
- `unknown`

原始库错误先映射为标准原因，无法确定时使用 `unknown` 并保留经过脱敏和截断的 `close_detail`。

## 6. 内存注册中心

`ConnectionSessionRegistry` 建议为进程级服务，以 `channel_id` 和协议连接键建立索引；每次协议服务启动生成新的 `server_instance_id`。

关键接口建议：

```python
open_session(channel_id, protocol_type, connection_key, endpoints, metadata) -> session_id
mark_established(session_id, identity=None, security=None)
record_activity(session_id, rx_bytes=0, tx_bytes=0, rx_messages=0, tx_messages=0)
close_session(session_id, reason, initiator, detail=None) -> bool
close_server_sessions(channel_id, server_instance_id, reason="server_stopped")
snapshot_current(channel_id) -> tuple[ConnectionSnapshot, ...]
snapshot_summary(channel_id) -> ConnectionSummary
```

工业实现要求：

- 使用 `threading.RLock` 或等价同步机制保护状态；不得假定所有协议回调都在同一事件循环。
- 对外只返回不可变快照，不把内部可变对象或原生连接句柄暴露给 API。
- 连接键仅在进程内使用；数据库不得保存 Python 对象地址、socket 或 C 指针。
- `close_session` 使用“首次关闭生效”语义，后续重复调用返回 `False`，不重复计数和落库。
- 活动计数可以聚合更新，避免每个报文产生一个持久化事件。
- 事件队列必须有上限并暴露丢弃/积压指标；连接关闭事件优先级高于活动检查点。

## 7. 数据库与保留策略

### 7.1 新表

新增 `connection_session` 表，不复用业务报文或日志表。建议列：

```text
id, session_id, channel_id, protocol_type, server_instance_id,
remote_ip, remote_port, local_ip, local_port,
transport_connected_at, established_at, last_activity_at,
disconnected_at, duration_ms, state,
disconnect_reason, disconnect_initiator, close_detail,
client_identity_json, security_json,
rx_bytes, tx_bytes, rx_messages, tx_messages, error_count,
end_time_accuracy, created_at
```

约束与索引：

- `session_id` 唯一。
- `channel_id` 外键关联 `channel.id`，设备删除时同步清理或由现有删除服务显式清理。
- 索引 `(channel_id, disconnected_at DESC)` 支持最近历史查询。
- 索引 `(channel_id, disconnect_reason, disconnected_at)` 支持异常统计。
- IP 使用字符串存储，长度至少 45；端口使用可空整数。
- JSON 字段沿用项目对 SQLite/MySQL 均兼容的序列化方式。

项目当前通过 `Base.metadata.create_all()` 建表，因此第一期新增表需同时在 `src/data/model/__init__.py` 或数据库模型加载入口显式导入。若后续需要修改既有列，再引入正式迁移工具，不在本功能中顺带改造全部数据库迁移体系。

### 7.2 写入策略

- 打开连接时可写入一条 `ESTABLISHED` 记录，断开时更新完整结果；这样能在非正常进程退出后识别未闭合记录。
- 协议回调只向有界队列提交事件，由独立后台任务和独立 SQLAlchemy Session 批量写入。
- `last_activity_at` 与流量累计按不短于 30 秒的间隔检查点写入，避免高频数据库更新。
- 正常服务停止时先关闭会话，再在限定时间内刷新持久化队列；超时必须记录告警但不能无限阻塞退出。

### 7.3 最近 100 条

保留规则按 `channel_id` 隔离，只计算已结束连接：

1. 提交新历史记录。
2. 按 `disconnected_at DESC, id DESC` 排序保留最新 100 条。
3. 在同一数据库事务内删除该设备更早的记录。

不要使用全局 100 条，否则多个设备会相互挤占历史。当前连接不占用 100 条额度。

### 7.4 异常恢复

应用启动时扫描上次进程遗留的未闭合记录：

- 标记为 `ABNORMAL`、`disconnect_reason=process_terminated`、`disconnect_initiator=process`。
- 无法知道真实断开时刻时，`disconnected_at` 为空，`end_time_accuracy=estimated`，持续时间计算到最后活动检查点。
- API 必须允许断开时间为空，前端显示“进程退出，时间未知”，不能伪造精确时间。

## 8. API 设计

沿用当前设备接口以 POST + `device_name` 查询的风格，建议增加：

### 8.1 `POST /api/devices/connection-summary`

请求：

```json
{"device_name": "IEC104-Server-1"}
```

响应：

```json
{
  "supported": true,
  "server_running": true,
  "current_count": 2,
  "active_count": 1,
  "idle_count": 1,
  "history_count": 100,
  "abnormal_disconnects_today": 1,
  "updated_at": "2026-08-23T10:20:30.123+08:00"
}
```

### 8.2 `POST /api/devices/current-connections`

返回当前连接数组，默认按 `transport_connected_at DESC` 排序。字段至少覆盖：

`session_id`、协议、远端/本地端点、状态、连接时间、实时持续时间、最近活动时间、收发统计、安全摘要、客户端身份。

### 8.3 `POST /api/devices/connection-history`

请求支持：

```json
{
  "device_name": "IEC104-Server-1",
  "page": 1,
  "page_size": 20,
  "disconnect_reason": null,
  "remote_ip": null
}
```

- `page_size` 最大 100。
- 默认按断开时间倒序。
- 返回 `total`、`items` 和当前保留上限 `retention_limit`。
- IP 筛选必须参数化查询，不做字符串拼接。

### 8.4 `POST /api/devices/connection-detail`

按 `device_name + session_id` 返回一条当前或历史详情，防止跨设备读取。

### 8.5 兼容与错误语义

- 可在现有 `/api/devices/info` 响应中增补 `connection_monitoring_supported` 和 `current_connection_count`，但不改变原 `server_status` 含义。
- 对客户端模式、串口、Modbus UDP、GOOSE 返回 `supported=false`；若直接请求列表，可返回空集合并附 `unsupported_reason`，不使用伪造数据。
- 设备不存在返回 404；参数不合法返回 422；服务未启动是合法状态，返回 200 和空当前连接。
- 第一期前端使用 3～5 秒轮询即可；本期不引入 WebSocket。若以后设备规模和实时性要求提高，再基于同一注册中心增加事件推送。

## 9. 各协议接入方案

### 9.1 Modbus TCP / RTU over TCP

现有 `CaptureRequestHandler` 已具备连接、数据、断开回调和 `peername` 提取能力，是第一批接入对象。

- `callback_connected` 创建会话并记录远端/本地端点。
- `callback_data` 只聚合活动时间和字节/报文计数。
- `callback_disconnected` 映射断开原因并关闭会话。
- 空闲超时映射 `idle_timeout`；超过最大连接数的拒绝可作为“拒绝事件”统计，但不进入已连接历史，避免语义混淆。
- TLS 模式补充安全摘要，不记录私钥、密码或完整证书原文。

### 9.2 DL/T 645 TCP

已固定 `dlt645[async]==3.2.0`，通过其向后兼容的 `on_connect`、`on_activity`、`on_disconnect` 回调接入。TCP 模式记录生命周期与流量，串口模式明确返回不支持；不修改 `.venv` 中的包文件。

### 9.3 DNP3 TCP Server

当前 `pydnp3-pure` TCP Server 为单活动连接，新连接可能替换旧连接。

- 在本仓库增加 `TrackedTcpServer` 适配器，复用原协议实现并暴露生命周期与本地/远端端点。
- 新连接替换旧连接时，旧会话使用 `connection_replaced` 结束。
- `finally` 路径保证异常和正常断开都会进入统一关闭流程。

### 9.4 IEC 61850 MMS

使用 `pyiec61850-ng` 的 `IedServer_setConnectionIndicationHandler` 接入，并通过 `ClientConnection_getPeerAddress` 获取对端地址。

- 原生连接对象只用于回调期间提取信息，不能跨线程保存在 API DTO 或数据库。
- 回调中的 connected/disconnected 状态映射到统一会话。
- 若库只返回 IP、不返回端口，端口保持 `null`，不猜测客户端源端口。
- 当前 SWIG 包装不接受普通 Python callable 时，通过受控的 `ctypes` C ABI 适配器注册同一个原生回调。

### 9.5 IEC 60870-5-104

已固定个人 fork `600888/iec104-python@c7ea3988`，该版本提供精确的逐连接状态回调和历史元数据：

- 暴露稳定的单连接 ID、远端/本地端点。
- 暴露连接状态变化/断开回调和底层错误原因。
- TLS 握手成功后再标记 `ESTABLISHED`，握手失败记录规范错误。

单向 TLS 使用 `TlsServerBridge` 时，后端协议连接可能只看到环回地址。必须在 bridge 接收真实客户端时采集远端端点，并用内部关联 ID 传递给 IEC104 适配层。不能把 `127.0.0.1` 当成真实客户端，也不能通过轮询总连接数推断某一条连接的起止时间。

## 10. 实施阶段

### Phase 0：契约与依赖验证

- 冻结统一字段、状态和断开原因枚举。
- 用小型探针验证五种协议在正常断开、复位、服务停止、TLS 失败时能获得哪些事件。
- 优先完成 IEC104 断开回调和 TLS bridge 真实端点的可行性验证。
- 确认 `.pen/server-monitor.pen` 中字段、空值、状态颜色和刷新频率与 API 契约一致。

完成标准：每种纳入协议都有明确事件来源和缺失字段说明，不依赖猜测或轮询计数。

### Phase 1：公共核心、数据库与 API

- 实现会话模型、注册中心、持久化队列、ORM 表和恢复/保留逻辑。
- 扩展 `ServerHandler` 能力接口。
- 使用 fake adapter 完成 API 和前端联调，不等待全部协议接入。
- 加入结构化日志和基础内部指标。

### Phase 2：Modbus 接入

- 接入 Modbus TCP 和 RTU over TCP。
- 验证多客户端、空闲超时、最大连接数、服务停止和 TLS 场景。

### Phase 3：DL/T 645 与 DNP3 接入

- 完成依赖 fork/adapter 改造并固定版本。
- 验证 DNP3 新连接替换、DL/T 645 多连接及异常释放。

### Phase 4：IEC 61850 MMS 接入

- 接入原生连接指示回调。
- 验证重复回调、服务停止和原生对象生命周期安全。

### Phase 5：IEC104 接入

- 完成 c104 逐连接生命周期扩展。
- 解决普通 TCP、双向 TLS、单向 TLS bridge 的真实端点关联。
- 在该能力可靠前，不对 IEC104 发布不完整的历史功能。

### Phase 6：全量验证与发布

- 完成 SQLite/MySQL、IPv4/IPv6、前后端联调和压力测试。
- 补充用户文档、API 文档、版本升级说明和故障排查项。
- 使用功能开关灰度启用；确认稳定后默认开启。

## 11. 测试计划

### 11.1 单元测试

- 同一 IP 不同端口、同一端口快速重连生成独立 session。
- 并发 connect/activity/disconnect 无重复、无丢失、无负持续时间。
- `close_session` 幂等；服务停止与远端关闭竞态只生成一条历史。
- 系统时间回拨不影响持续时间。
- 第 101 条历史写入后只保留最新 100 条，且不同设备互不影响。
- 事件队列满载时关闭事件优先，积压指标可观察。

### 11.2 数据库与 API 测试

- SQLite 和 MySQL 均能建表、查询、分页、过滤和保留。
- 设备不存在、不支持协议、服务未运行等响应语义正确。
- IPv6、空端口、空断开时间、Unicode 详情可正确序列化。
- 设备删除无孤立历史；所有筛选参数均使用 ORM 参数化查询。
- 应用重启后遗留会话按 `process_terminated` 恢复。

### 11.3 协议集成测试

每个协议至少覆盖：

- 正常连接/主动断开。
- 客户端进程被杀、网络复位、半开连接或空闲超时。
- 服务端停止、快速重启、连续快速重连。
- 多客户端并发（协议支持时）。
- TLS 成功、证书失败和握手超时（协议支持时）。
- 收发计数和最近活动时间随真实报文变化。

### 11.4 性能与稳定性

- 连接事件回调只做内存更新和队列提交，目标 P95 小于 1 ms，不阻塞协议 IO。
- 模拟至少 1,000 次快速连接/断开，内存不随历史持续增长。
- API 高频轮询不加锁等待协议线程，不触发数据库高频写。
- 后台持久化失败时有退避、告警和有限重试；不得无限增长内存队列。

## 12. 可观测性与安全

建议增加结构化日志/指标：

- 当前连接数、连接总数、断开总数、异常断开数。
- 每协议和每设备的连接峰值。
- 持久化队列深度、丢弃事件数、写入延迟和失败数。
- 未识别断开原因数，便于持续完善协议映射。

安全要求：

- API 复用现有授权边界；若后续加入用户权限，按设备进行访问控制。
- IP 和客户端身份按运维数据处理，日志导出和接口响应遵循最小权限。
- 不采集完整业务报文、密码、私钥或认证令牌。
- `close_detail` 限长并清理控制字符，避免日志注入和超大错误占库。

## 13. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| IEC104 缺少逐连接断开回调 | 无法准确生成历史 | 先改固定 fork 并完成依赖探针，禁止轮询计数推断 |
| TLS bridge 隐藏真实客户端地址 | 显示环回 IP | 在 bridge 入口采集并通过关联 ID 传递 |
| 原生回调线程不确定 | 死锁或拖慢协议 | 回调仅做线程安全内存操作和非阻塞入队 |
| 高频报文导致写放大 | 数据库压力 | 活动聚合、30 秒检查点、断开时最终刷新 |
| 应用异常退出 | 结束时间不准确 | 启动恢复并显式标记 `estimated`，不伪造精确值 |
| 依赖包改动难维护 | 升级冲突 | 在项目 fork 实施最小向后兼容改动并固定 commit |

## 14. 验收标准

- 所有纳入协议能准确区分“服务运行”和“客户端在线”。
- 当前连接在一个前端轮询周期内出现/消失，IP、端口、起始时间和持续时间正确。
- 正常与异常断开均进入历史，断开时间、最终时长和规范原因可解释。
- 每台设备始终只保留最近 100 条已结束连接，重启后仍成立。
- 同 IP 多连接、快速重连、服务停止、TLS bridge、IPv6 不串会话。
- Modbus UDP、GOOSE、串口和客户端模式不产生伪连接。
- 协议 IO 不因数据库故障或前端查询而阻塞。
- `.pen/server-monitor.pen` 中当前连接、历史连接和详情字段均有明确 API 来源及空值表现。

## 15. 推荐开发任务拆分

- [x] 定义 DTO、状态、断开原因与前端字段映射。
- [x] 完成各协议生命周期能力探针，形成验证记录。
- [x] 实现 `ConnectionSessionRegistry` 及并发单测。
- [x] 新增 ORM 模型、持久化队列、恢复和最近 100 条策略。
- [x] 扩展 `ServerHandler` 与设备查询服务。
- [x] 实现 summary/current/history/detail API。
- [x] 按 Modbus → DL/T 645/DNP3 → MMS → IEC104 顺序接入。
- [ ] 完成数据库、协议集成、压力与前端联调测试。
- [ ] 补充配置、日志指标、使用文档和发布说明。

第一批开发建议完成 Phase 0～2：先交付可复用的公共核心和 Modbus 端到端闭环，同时把 IEC104 的依赖风险提前验证清楚，再并行推进其余协议。

> 2026-08-23 实施记录：公共核心、SQLite 持久化、四个查询 API 及五类网络服务端协议已接入；全量自动化测试为 776 通过、25 跳过。MySQL、千次连接压力、前端联调和发布文档仍按 Phase 6 推进。
