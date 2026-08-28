# DNP3 未实现功能盘点与优先级实施计划

> 基线日期：2026-08-28
> 实现基线：`pydnp3-pure` 固定到提交 `83c0365b9ce645f4789ab53a281aeb7c00dda309`
> 范围：EMS Simulate 的 DNP3 Master、Outstation、Handler、运行参数、测点模型、报文查看与自动化测试

## 1. 结论

当前 DNP3 已具备 TCP 连接、四遥点注册、Class 0/事件轮询报文发送、基础读缓存、Direct Operate/SBO 报文发送、基础事件缓冲和三层报文解析，适合继续迭代，但还不能视为完整、可靠的 DNP3 实现。

应优先处理的不是继续增加对象组，而是先补齐以下基础闭环：

1. 请求必须等待并匹配响应，超时、重试和命令状态必须真实返回；
2. 修正默认地址、连接状态、断线重连和错误可观测性；
3. 实现指定地址读取，避免单点读取退化成 Class 0 全量轮询；
4. 修复 SBO 状态机、越界地址、稀疏地址和大于 255 的点索引；
5. 让界面上的 DNP3 参数真正生效，不能继续保留“可配置但运行时忽略”的参数；
6. 再完成事件确认、未请求上报、时间同步、品质/时标和扩展对象组。

优先级定义：

| 优先级 | 含义 |
| --- | --- |
| P0 | 影响基本正确性、操作结果可信度或与第三方设备互操作，发布前必须完成 |
| P1 | DNP3 常用生产能力，完成后可作为功能完整的常规 Master/Outstation 使用 |
| P2 | 增强互操作、规模和部署能力，可分版本交付 |
| P3 | 高级标准能力或低频场景，按项目需求实现 |

## 2. 当前实现边界

### 2.1 已实现

| 能力 | 当前状态 |
| --- | --- |
| TCP Master / Outstation | 已实现，Outstation 当前只保留一个活动连接 |
| DNP3 16 位链路地址 | 已实现，链路帧固定使用 2 字节地址 |
| Class 0 完整性轮询 | Master 可发送，Outstation 可返回 G1/G10/G20/G21/G30/G40 |
| Class 1/2/3 事件轮询 | Master 可发送；Outstation 有基础 BI/AI 事件缓冲 |
| 四遥映射 | YC→G30/G32、YX→G1/G2、YK→G10/G12、YT→G40/G41 |
| 遥控/遥调 | 可发送 Direct Operate；二进制控制可发送 Select + Operate |
| 传输层分片 | `pydnp3-pure` 支持传输分段和重组 |
| 报文查看 | 支持链路层、传输层、应用层、对象组/变体、地址、值、品质和时间戳解析 |
| 报文捕获 | TX 按链路帧捕获；RX 当前按 TCP `read()` 数据块捕获 |
| 测点批读 | 一次 Class 0 轮询后从缓存映射多个点 |

### 2.2 当前“看似实现但没有形成闭环”的能力

| 能力 | 实际问题 |
| --- | --- |
| 请求成功返回 | 多数方法在报文写入 socket 后立即返回成功，没有等待对应响应 |
| `command_timeout_ms` / `max_retries` | 参数传入了 `MasterConfig`，但当前 Master 会话没有超时和重试状态机 |
| 指定点读取 | `read_point_active()` 实际发送 Class 0 全量轮询，再固定等待 200 ms 读缓存 |
| SBO | Outstation 的 Select 始终返回成功，没有保存选择对象、值和过期时间；Operate 不校验 Select |
| 未请求上报 | Outstation 可以接受 Enable/Disable，但事件变化后不会主动发送 Unsolicited Response |
| 事件确认 | `WAIT_CONFIRM` 状态没有进入路径，事件不会按确认正确移除，可能被重复返回 |
| 自动完整性/事件轮询 | 间隔写入 `MasterConfig`，但会话没有根据间隔创建调度任务 |
| 时间同步 | 客户端 `sync_time()` 固定返回 `False`；Outstation 的 G50 写入未实现 |
| 连接超时 | `connection_timeout_ms` 未应用到 TCP 建连 |
| 最大连接数 | `max_connections` 未使用，新的 Master 会替换旧连接 |
| Link/App Confirm | 界面参数存在，但发送链路和应用层状态机未按参数工作 |
| 地址长度 | 界面允许 1/2 字节，但当前库固定为标准 DNP3 的 2 字节链路地址 |

## 3. P0：基本正确性与互操作阻断项

### DNP3-P0-01 修正地址默认值和地址校验

当前客户端默认参数为 `local_address=1, remote_address=0`，服务端也是 `local_address=1, remote_address=0`。标准自测组合应是：

- Master：本地地址 0，对端 Outstation 地址 1；
- Outstation：本地地址 1，对端 Master 地址 0。

当前链路层没有严格校验目的/源地址，因此错误默认值可能在本系统自测中被掩盖，但连接第三方设备时会直接失败。

实施内容：

- 修正后端和前端 DNP3 Client 默认地址；
- LinkLayer 接收时校验目的地址、源地址和广播地址；
- 地址不匹配时记录结构化诊断，不进入应用层；
- 增加默认配置 Master↔Outstation 端到端测试。

验收：默认创建的客户端和服务端无需修改地址即可互通；错误地址不会误处理报文。

### DNP3-P0-02 建立请求—响应事务管理器

当前 Master 只有 4 位应用序号递增，没有 pending request、响应匹配、超时和重试。读、控制、启停未请求等接口无法判断真实执行结果。

实施内容：

- 为每个请求保存序号、功能码、目标对象、发送时间、重试次数和 `Future`；
- 按应用序号及响应对象匹配 solicited response；
- 使用 `command_timeout_ms` 和 `max_retries`；
- 超时后返回明确错误类型，触发 `on_timeout` 和日志；
- 限制并发请求数，处理 4 位序号回绕；
- 区分发送成功、响应成功、IIN 异常、命令状态失败和超时。

验收：接口只在收到匹配响应后返回成功；丢包、迟到响应和错误序号均有自动化覆盖。

### DNP3-P0-03 实现真正的指定地址读取

当前单点读取会发 Class 0 全量轮询并固定等待 200 ms，存在耗时随站点规模增长、拿到旧缓存、慢设备误判失败等问题。

根因之一是 `pydnp3-pure.app.fragment.parse_fragment()` 不区分 READ 的“对象选择头”和响应中的“对象值”，带地址范围的 READ 请求会被错误地当成对象数据解析。

实施内容：

- 在 `pydnp3-pure` 中按功能码区分选择对象与值对象；
- Master 增加通用 `send_read(group, variation, start, stop)`；
- 单点读取发送一个点的范围请求并等待匹配响应；
- 批量读取按对象组和连续地址合并；点较密集时允许使用 Class 0，由策略自动选择；
- 使用缓存版本号或响应事务 ID，禁止固定 `sleep(0.2)` 判断新鲜度。

验收：读取 index=100 时只请求对应对象范围；慢于 200 ms 的正常响应仍可成功。

### DNP3-P0-04 让遥控/遥调结果可信，并补齐 SBO 状态机

当前 Direct Operate、Select 和 Operate 只要发送未抛异常就返回成功；Outstation 对不存在的点也可能返回成功。Select 没有锁定状态，Operate 不校验是否存在匹配且未超时的 Select。

实施内容：

- Master 解析 G12/G41 响应中的 `CommandStatus` 并返回结果；
- Outstation 在点不存在、类型不匹配、参数非法时返回对应状态；
- Select 保存 Master、对象组、index、值/控制块、时间和序号；
- Operate 校验 Select 内容与 `select_timeout_s`，防止跨 Master 或不同值执行；
- 支持取消、超时清理、重复 Operate 和 Direct Operate No Ack 的正确语义；
- 从测点 `command_type` 和 DNP3 点配置选择 Latch/Pulse/Trip/Close、SBO/DO、模拟量变体。

验收：无 Select 的 Operate 返回 `NO_SELECT`；不存在的 index 不更新测点；客户端能展示具体失败状态。

### DNP3-P0-05 完善连接生命周期与重连

当前客户端断线后只把底层 `_running` 置为 false，没有通知 Handler；没有连接超时、重连退避和会话重置，界面运行状态可能与真实 socket 状态不一致。

实施内容：

- TCP Client 增加 on_connect/on_disconnect/on_activity 回调；
- 应用 `connection_timeout_ms`，增加可配置的重连退避；
- 断线时失败所有 pending request，清理 transport reassembler 和会话状态；
- Handler 连接监控与现有统一连接详情接口对齐；
- 停止设备时取消轮询、重连和超时任务，保证无后台泄漏。

验收：拔网线、服务端重启、连接拒绝和半开连接均能正确反映状态并恢复。

### DNP3-P0-06 修复 RX 报文捕获边界

当前 `_on_rx(data)` 在 TCP `read()` 回调处直接捕获。TCP 数据块可能包含半帧或多帧，因此报文查看可能记录为无效 DNP3 帧，后续解析和请求响应关联都会不稳定。

实施内容：

- 把 RX 捕获移动到 LinkLayer 成功组帧之后；
- 保留原始 wire frame（包含各 CRC），不要只保存去 CRC 后的 `LinkFrame`；
- 一条捕获记录对应一条 DNP3 链路帧；
- 为粘包、拆包、一次读取多帧增加测试；
- 多传输分段增加 fragment correlation id，详情中可跳转同一应用报文的所有链路帧。

验收：任意 TCP 拆包方式都生成相同的报文列表和解析结果。

### DNP3-P0-07 支持稀疏地址和 16 位 index

Outstation 当前大量使用 `RANGE_8_START_STOP`，并假设列表从首地址到末地址连续。稀疏点会产生“范围数量与实际点数不一致”，index>255 也无法编码；控制命令同样固定使用 `INDEX_8`。

实施内容：

- 连续范围根据最大地址自动选择 RANGE_8/RANGE_16；
- 稀疏点改用 INDEX_8/INDEX_16，或拆成多个连续对象头；
- 控制命令根据 index 自动选择 INDEX_8/INDEX_16；
- 对超出 0～65535 的点在导入/创建阶段拒绝；
- Class 0、事件响应、指定范围读、SBO/DO 全路径覆盖 index 255/256/65535。

验收：地址 1、100、300 的三个点能被第三方 Master 正确读取，不产生伪造的连续范围。

### DNP3-P0-08 清理静默异常和无效配置

当前发送、接收缓存和命令路径有多处 `except Exception: pass/return False`，无法区分协议失败、网络失败和实现错误。

实施内容：

- 所有吞异常路径改为带设备、方向、功能码、序号的结构化日志；
- 对用户可见操作返回稳定错误码；
- 对尚未生效的配置先隐藏或标注“不支持”，避免虚假能力；
- 建立运行参数“声明—消费—测试”检查表，新增参数必须有消费点和测试。

验收：失败操作在日志和 API 中能定位原因；界面不再展示完全无效的开关。

## 4. P1：常用 DNP3 功能闭环

### DNP3-P1-01 事件确认与未请求上报

- 修复事件发送后进入 WAIT_CONFIRM 的状态迁移；
- 只确认本次响应包含的事件，不能 `confirm_all()` 清空其他 Class；
- 事件溢出设置 IIN2 `EVENT_BUFFER_OVERFLOW`；
- 值变化时记录真实 UTC 时间戳并选择 G2/G32 带时标变体；
- `enable_unsolicited` 为真且连接可用时主动发送未请求响应；
- 支持 CON、确认超时、重发、禁止未请求和启动时 Null Unsolicited；
- 输出状态变化是否产生事件需形成明确策略并覆盖 G11/G42（如库支持后启用）。

### DNP3-P1-02 统一轮询调度所有权

目前产品级“自动读取”已经会触发 DNP3 Class 0，`integrity_interval_s/event_interval_s` 又出现在协议配置中，但底层会话没有真正调度。应避免两个调度器重复轮询。

建议方案：

- 产品自动读取间隔负责 Class 0 数据刷新；
- DNP3 `event_interval_s` 仅负责 Class 1/2/3 事件维护；
- 删除或只读展示 `integrity_interval_s`，除非明确提供独立的协议轮询模式；
- 轮询任务统一归 Handler 生命周期管理，可启动、暂停、取消并显示最近一次结果；
- 同时启用未请求上报时，事件轮询采用低频兜底策略。

### DNP3-P1-03 时间、延迟、重启与冻结

- Master 实现 Delay Measure + G50 时间写入的时间同步流程；
- `time_sync_enabled` 真正生效，并记录同步结果；
- Outstation 支持 G50V1 写时钟及 NEED_TIME IIN；
- Delay Measure 返回真实 G52 延迟值，而不是只有对象头；
- Cold/Warm Restart 返回标准延迟对象，并提供模拟行为；
- Freeze/Freeze Clear/No Ack 调用真实计数器冻结逻辑，支持指定范围。

### DNP3-P1-04 点级 DNP3 配置

当前 `Dnp3Server.add_points()` 只传 index，测点无法配置下列 DNP3 语义：

- 静态变体、事件变体；
- Event Class 1/2/3；
- Analog deadband；
- SBO/DO、CROB 操作类型及脉冲时间；
- 初始品质、是否产生事件、时间戳模式。

需要扩展测点持久化、导入导出、前端表单、Handler 注册和复制设备流程，并保持旧数据默认值兼容。

### DNP3-P1-05 品质、时标与缓存元数据

- Master 缓存不能只保存 value，应保存 group、variation、index、flags、timestamp、接收时间和来源（轮询/未请求）；
- 将 DNP3 品质映射到统一品质展示，但保留原始 flags；
- 提供点级元数据读取接口，和 IEC 61850 的品质/时标查看体验一致；
- 缓存增加有效期，断线后标记通信丢失，禁止无提示返回旧值。

### DNP3-P1-06 链路层确认与应用确认

- 实现 RESET_LINK、REQUEST_LINK_STATUS、LINK_STATUS；
- 实现 CONFIRMED_USER_DATA 的 FCB/FCV、ACK/NACK、超时和重发；
- `link_confirm` 控制选择 confirmed/unconfirmed user data；
- `app_confirm` 控制需要确认的应用响应，并与事件确认状态机统一；
- 支持广播地址的无确认/确认限制。

### DNP3-P1-07 报文关联和解析补全

- 关联 READ 与 RESPONSE、SELECT 与 OPERATE、命令与状态响应；
- 同一应用 fragment 跨多个链路帧时在详情中重组展示；
- 完善链路控制字、IIN、限定词和错误说明；
- 增加 G11/G13/G22/G23/G31/G33/G34/G42/G43/G51/G52 等已实现运行能力对应的解析；
- 对未知对象保留原始数据和偏移，不因一个对象未知而放弃后续可解析对象。

### DNP3-P1-08 端到端与第三方互操作测试

- 本系统 Master ↔ 本系统 Outstation TCP 实际连接测试；
- 使用随机 TCP 拆包、粘包和延迟注入；
- 覆盖 Class 0、Class 1/2/3、指定点读、DO、SBO、未请求、时间同步和断线恢复；
- 至少选一个独立实现进行互操作测试，避免双方共享同一库掩盖协议错误；
- 保存互操作抓包作为解析器回归样本。

## 5. P2：规模、部署与扩展能力

| 编号 | 功能 | 说明 |
| --- | --- | --- |
| DNP3-P2-01 | 应用层分片/多 fragment 响应 | `max_fragment_size` 当前未实际限制；大站点响应需切分并按 CON/SEQ 发送 |
| DNP3-P2-02 | 多 Master / 多连接 | 每个连接独立 Link/Transport/Application/OutstationSession，落实 `max_connections` |
| DNP3-P2-03 | TLS | 复用项目证书配置，为 TcpClient/TcpServer 构建 SSLContext；需与 Secure Authentication 区分 |
| DNP3-P2-04 | 串口链路 | 增加 serial channel、串口重连、半双工时序与报文捕获 |
| DNP3-P2-05 | Counter/Frozen Counter 产品化 | 增加累计量测点模型或明确映射策略，支持 G20/G21/G22/G23 和冻结命令 |
| DNP3-P2-06 | 变体协商与响应策略 | 按请求 variation 返回，支持 variation=0 默认变体选择，而不是固定 G30V5/G40V3 |
| DNP3-P2-07 | Double-bit、Deadband、输出事件 | 增加 G3/G4、G11/G13、G34、G42/G43 等常用对象 |
| DNP3-P2-08 | 大规模性能 | 万点数据库、事件缓冲、批量序列化、报文列表内存和轮询延迟基准 |

## 6. P3：高级标准能力

| 功能 | 建议 |
| --- | --- |
| DNP3 Secure Authentication v5 | 作为独立安全项目，不用 TLS 代替；涉及 G120、挑战/响应、密钥更新和审计 |
| 文件传输 | 按真实需求实现 G70 和文件操作功能码，默认不作为四遥模拟器发布门槛 |
| Octet String / Virtual Terminal | 按设备互操作需求增加 G110～G113 |
| Assign Class 完整实现 | 支持 Master 动态修改点事件类并持久化/重启恢复 |
| Device Attributes | 增加设备能力和身份对象，便于第三方 Master 发现 |
| 一致性测试 | 建立 IEEE 1815 conformance profile、模糊测试和长时间稳定性测试 |

## 7. 运行参数处理计划

在实现前先把当前参数分为“已生效、待实现、应移除”，避免继续扩散无效配置。

| 参数 | 当前状态 | 计划 |
| --- | --- | --- |
| `local_address` / `remote_address` | 已传入协议栈，但默认值错误且接收不校验 | P0 修正默认值并校验 |
| `address_size` | 未使用，当前链路固定 2 字节 | 从界面和默认配置移除；如保留需说明仅兼容旧配置 |
| `link_confirm` | 未使用 | P1 完成链路确认状态机前标记不支持 |
| `app_confirm` | 未使用 | P1 与事件确认一起实现 |
| `time_sync_enabled` | 未使用 | P1 实现时间同步后启用 |
| `integrity_interval_s` | 仅存入配置，无底层调度 | 与产品自动读取合并，避免重复调度 |
| `event_interval_s` | 仅存入配置，无底层调度 | P1 作为事件轮询任务生效 |
| `enable_unsolicited` | Master 不自动发送 enable；Outstation 不主动上报 | P1 完成完整闭环 |
| `connection_timeout_ms` | 未使用 | P0 应用到建连和连接状态机 |
| `command_timeout_ms` | 传入但未消费 | P0 由事务管理器消费 |
| `max_retries` | 传入但未消费 | P0 由事务管理器消费 |
| `event_buffer_size` | 已用于三个 Class 的队列大小 | 保留，并补溢出 IIN 与分类配置 |
| `select_timeout_s` | 传入但没有 Select 状态 | P0 由 SBO 状态机消费 |
| `max_connections` | 未使用，实际单连接 | P2 多 Master 前标记为不支持 |

## 8. 推荐实施顺序

### 里程碑 M0：配置与测试基线

- 完成 P0-01、P0-08；
- 建立 Master↔Outstation 真实 TCP 测试夹具；
- 为现有行为录制抓包，固定回归基线。

### 里程碑 M1：可信请求与可靠连接

- 完成 P0-02、P0-03、P0-05、P0-06；
- 所有读操作取消固定 sleep；
- API 能区分响应、超时和断线。

### 里程碑 M2：控制与地址正确性

- 完成 P0-04、P0-07；
- 覆盖稀疏点、16 位 index、DO/SBO 和失败状态；
- 与独立 DNP3 实现验证基本读控。

### 里程碑 M3：事件与时间能力

- 完成 P1-01～P1-05；
- 未请求、事件轮询、时间同步和品质/时标形成产品闭环；
- 清理界面所有无效参数。

### 里程碑 M4：链路互操作与扩展

- 完成 P1-06～P1-08；
- 再按需求选取 P2 项，不应在 P0/P1 未完成前优先增加冷门对象组。

## 9. `pydnp3-pure` 与本项目的修改边界

以下能力应优先在 `pydnp3-pure` 仓库实现，然后更新 `pyproject.toml` 和 `uv.lock` 的固定提交：

- 功能码感知的应用对象解析；
- Master pending request、响应匹配、超时和重试；
- Outstation SBO、事件确认、未请求状态机；
- 链路层确认、地址过滤、应用分片；
- 新对象组/变体和序列化能力；
- TCP channel 生命周期回调和 TLS/Serial channel。

以下能力留在 EMS Simulate：

- 四遥及测点字段映射；
- 自动读取与事件轮询调度策略；
- 运行参数归一化和前端配置；
- 点值、品质、时标与工程值映射；
- 报文展示、设备日志、连接监控和 API 错误码；
- 产品级端到端测试与第三方互操作样例。

禁止直接修改 `.venv/Lib/site-packages` 作为正式实现；所有底层改动必须进入依赖仓库并固定到可复现提交。

## 10. 完成标准

DNP3 常规能力达到“完成”至少需要满足：

- 默认 Master/Outstation 配置可直接互通；
- 所有读控接口基于匹配响应返回结果，不使用固定等待猜测成功；
- 0～65535 的连续和稀疏 index 正确编码；
- DO/SBO 成功和失败状态均真实可见；
- Class 0、Class 1/2/3、事件确认和未请求上报无重复丢失；
- 时间同步、品质和时间戳可查看；
- TCP 拆包/粘包不影响协议处理和报文解析；
- 断线重连无任务泄漏、无旧缓存误报；
- 每一个可见运行参数都有实际消费点和自动化测试；
- 通过本系统自环测试和至少一个独立实现的互操作测试。
