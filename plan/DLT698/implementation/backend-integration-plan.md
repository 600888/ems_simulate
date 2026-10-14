# DL/T 698.45 后端接入实施计划

日期：2026-10-14
范围：为 `.pen/dlt698.pen` 对应的前端提供真实协议运行时和 HTTP 接口。本文是后续实施计划，不表示本次已实现 DL/T 698 后端或设备通信。

## 1. 实施基线与交付边界

本次前端以现有设备页、连接配置、报文窗口、连接监控、测点详情与模拟配置为公共入口，设计稿用于功能和交互参考。协议专属工作区包含普通对象、记录、REPORT、PROXY 和关联配置，不复制一套公共设备管理接口。

接口基线为 [types/dlt698.ts](../../../front/src/types/dlt698.ts)、[api/dlt698Api.ts](../../../front/src/api/dlt698Api.ts)、[utils/dlt698.ts](../../../front/src/utils/dlt698.ts)，语义依据为 [设计实施说明](../../../.pen/dlt698-design-spec.md)。接口文件是**拟定契约**，尚无配套路由；演示点表和预览草稿不可作为真实运行结果、能力探测或持久化数据。

已只读核对本机 `E:/github_project/dlt698/python/src/dlt698/` 下 `app/client.py`、`app/async_client.py`、`app/server.py`、`app/async_server.py`、`_native.pyi`、`standard/__init__.py`、`service/__init__.py`、`expert/__init__.py` 及 README/implementation-audit。对当前实现存在的入口直接引用；未验证 wheel 安装、真实电表互通、硬件串口或认证算法。本计划不修改该外部库。

## 2. 现有后端与改动位置

| 已有模块 | 核对结果 | 接入任务 |
| --- | --- | --- |
| [协议枚举](../../../src/enums/modbus_def.py) / [通道路由](../../../src/web/api/channel/router.py) | `ProtocolType` 无 Dlt698，`PROTOCOL_OPTIONS` 到 7 | 新增 `Dlt698Client`、`Dlt698Server`，通道协议 ID 预留 8；上线条件见下一节 |
| [ChannelService](../../../src/data/service/channel_service.py) | 根据 `(conn_type, protocol_type)` 映射；未知组合当前回退 `ModbusTcpServer` | 对 8 必须显式映射或报未接入，禁止进入默认 Modbus 分支 |
| [通道配置模型](../../../src/data/model/channel_configuration.py) / [配置服务](../../../src/data/service/channel_configuration_service.py) / [参数校验](../../../src/device/protocol/runtime_config.py) | `channel_protocol_params` 已支持版本化 JSON | 复用保存协议参数，新增 DLT698 参数归一化和强校验 |
| [设备构建器](../../../src/device/factory/general_device_builder.py) / [设备核心](../../../src/device/core/device.py) | 按具体协议创建处理器、导入点表和管理启动 | 增加 DLT698 初始化分支和生命周期，复制/删除/重载包含专属模型 |
| [处理器基类](../../../src/device/protocol/base_handler.py) | 同步读写、异步包装、公共报文与连接监控 | 新建 `src/device/protocol/dlt698_handler.py`；覆盖原生异步入口，不能依赖同步 float 读写桥 |
| [测点操作器](../../../src/device/core/point/point_operator.py) / [传统点表](../../../src/data/model/point_yc.py) | 值及换算路径具有 float/旧四类点表假设 | 增加 typed Data 适配，普通控件复用不等于值存储复用 |
| [自动读取](../../../src/device/auto_read/task_manager.py) | 已有不重叠任务、停止状态和读锁 | 复用任务管理，接入单会话请求仲裁和 typed Data 周期快照 |
| [公共连接注册](../../../src/device/core/connection/registry.py) / [持久化](../../../src/data/dao/connection_session_dao.py) | 当前/历史连接有统一生命周期 | DLT698 会话关联/断开事件映射到已有注册表，追加协商元数据 |
| [设备 API](../../../src/web/api/device/router.py) | 已有启动、停止、连接、报文、模拟、自动读取 API | 顶部按钮继续调用这些 API；专属 API 调同一服务，不能产生第二个运行时 |
| [FastAPI 应用](../../../src/web/app.py) / [统一响应](../../../src/web/api/schemas/base.py) | 按 router 注册，成功 code=200 | 新增并注册 `src/web/api/dlt698/router.py`，沿用错误处理中间件 |
| [数据库控制器](../../../src/data/controller/db_controller.py) | SQLite/MySQL 创建表并执行幂等迁移 | 注册专属模型及版本迁移，不能仅修改 Python 模型后假设旧库已升级 |
| [依赖清单](../../../pyproject.toml) | 尚无 `dlt698` 依赖 | 固定验证过的库提交/构建版本与平台 wheel，补 PyInstaller 资源和原生依赖 |

### 2.1 协议 ID 8 的预留与发布策略

1. 数字 8 仅分配给 DL/T 698，0～7 不重新编号；数据库 `channel.protocol_type=8` 与字符串协议枚举是不同概念。
2. 当前后端仍拒绝不在 `PROTOCOL_OPTIONS` 的 8。前端可显示独立预览入口、协议说明或禁用的候选项，不能伪造后端下拉返回值并向现有通道创建接口提交 8。
3. 首个后端阶段先提供状态/能力与配置持久化；依赖缺失、处理器未完成时显示 `available=false` 和原因。若允许存储 8，启动必须返回明确未接入错误。读取已有 8 的通道不得被误建为 Modbus。
4. 核心回环和迁移验收完成后，后端才公开 `{ "value": 8, "label": "DL/T 698.45", "conn_types": [0,1,2,3] }`。第一批支持常规主站 TCP 拨号/串口、表计 TCP 监听/串口；独立角色与 TCP 方向组合见 5.2。
5. 创建、编辑、复制、恢复、自动启动、协议切换全部使用同一协议 8 校验；通道删除显式清理专属记录，不把 SQLite 外键级联作为唯一保障。

## 3. 数据模型与迁移

### 3.1 采用专属 typed Data 存储

参考已有 [opcua_point 模型](../../../src/data/model/opcua_point.py) 的独立存储方式，增加以下模型和 DAO/Service。复用公共点表交互和测点编码，不将 Array/Structure 或 64 位值写入旧 `float real_value` 路径。

| 表/存储 | 关键字段和约束 | 用途 |
| --- | --- | --- |
| 现有 `channel_protocol_params` | `channel_id` 主键；`protocol_type=8`；`schema_version`；`params_json` | 角色、地址、关联、协商配置、设备布局；TCP/串口端点仍存在 `channel` |
| 新增 `dlt698_point` | `id`、`channel_id`、`schema_version`、`code`、`name`、`oad CHAR(8)`、`category`、`data_type`、`unit`、`scaler`、`standard`、`writable`、`initial_data_json`；唯一 `(channel_id,code)` | 点定义和服务端初值；允许不同编码引用相同 OAD，不把 OAD 全局唯一化 |
| 新增 `dlt698_point_runtime`，或受容量限制的内存快照 | `point_id`、`result_json`、`last_good_data_json`、`last_good_at`、`session_generation` | 保留当前错误和最后一次成功值；重启恢复值必须标记历史缓存，不能显示已在线读取 |
| 新增 `dlt698_record_set` / `dlt698_record_row` | `channel_id`、记录 OAD、模板、版本、真实列定义 JSON；行号、typed Data[]、创建时间；列序固定 | 本地记录管理，显式生成快照；记录不是普通对象点值 |
| 新增 `dlt698_object_binding` | `channel_id`、OI、schema、provider 类型、方法绑定标识、读写权限 | 专家服务对象目录；`point.writable` 只是业务请求，须与注册 schema/provider 一致 |
| 新增 `dlt698_route` | `channel_id`、TSA、目标配置标识、enabled | 可保存路由意图；运行时 `session_id` 和 bridge 状态不持久化成已连接 |
| 新增操作/报告审计存储或有界缓存 | 请求 ID、会话代次、服务、ordered items、结果、时间、完成状态 | SET/ACTION 结果未知恢复、逐项结果、REPORT 确认；设置容量/保留期限 |

`last_good` 与 `result` 是不同字段：DAR、超时、取消、标准校验错误更新 result，保留 last_good 及原时间，绝不写 0。标准校验失败收到的 Data 保留在 `result.data` 供原始详情检查，不能覆盖有效工程值。

### 3.2 迁移步骤

1. 在 `src/data/model/__init__.py` 注册模型，使新库 `Base.metadata.create_all` 创建完整表；专属表使用带版本的 JSON 类型/文本，JSON 内整数仍为字符串。
2. 为 SQLite 和 MySQL 增加幂等的 `_migrate_dlt698_schema()`，接在 `DbController` 初始化链；执行前通过 inspector 判断表/列/索引，显式记录错误，不吞掉除“已存在”外的 DDL 失败。
3. 升级旧库只创建表/版本记录，不推测某条 DLT645 或 YC 记录属于 DLT698，不自动替换现有点表。首次创建 8 的通道才写 DLT698 defaults。
4. 配置和点表创建/更新/导入使用事务；校验完整批次后提交。重命名 code 同时修改映射引用和自动读取配置；删除有引用的测点应拒绝或显式清理并返回影响，不静默留下悬空引用。
5. 通道复制复制点定义、初值、布局、明确配置的记录/映射；清空 sessions、运行结果、last_good 的在线标识、在途任务、REPORT 确认和运行路由。通道删除按事务顺序清理点、记录、目录、路由和配置。
6. 验收覆盖：全新 SQLite/MySQL、从当前 0～7 数据升级、连续启动两次、迁移失败恢复、复制/删除、协议切换、异常中断后的 JSON 完整性。备份与版本标识属于迁移交付内容。

## 4. OAD 与精确 Data 边界

### 4.1 地址与标准定义

- OAD 规范化为 8 位大写十六进制，不以十进制寄存器地址解码：OI 两字节、完整属性字节、元素索引一字节。保留属性特征位；自定义特征不能宣称经过标准目录验证。
- 索引 0 是完整属性、元素从 1 开始；`00100200` 是电能数组，`00100201` 是总量，`00100202` 是费率 1。分相电能通过 OI 选择，例如 `00110201`。
- 标准点表使用 `standard.objects/find_object/find_attribute/candidate_points/make_oad` 及 energy/phase/demand/harmonic 辅助入口，并由 `DeviceLayout` 校验 wiring、tariff_count、harmonic_order。电能标准属性按只读处理。
- 标准类型、倍率、单位取库定义，后端重新计算，不能相信客户端 `standard=true`、`writable=true` 或 scaler。自定义显示换算单独保存；不得修改标准倍率。
- TSA 和 SA 不是 DLT645 固定 6 字节 BCD 地址。在线业务仅 single 地址，组/广播/通配仅报文分析展示。服务器地址的 bytes 与 logical 分开传入 `ServerAddress`。

### 4.2 JSON ↔ 库 Data

`Dlt698Data` 使用 `{type,value}`，Array/Structure 的 value 为有序 typed children，不能转成逗号串或不带标签的 JSON 数组。后端建立 `data_from_json/data_to_json` 对称转换并拒绝隐式 Pydantic coercion。

| 类型 | 当前前端 JSON | 后端要求 |
| --- | --- | --- |
| Int8/UInt8/Int16/UInt16/Int32/UInt32/Int64/UInt64/Enum | 十进制整数字符串 | 严格范围、拒绝 bool/float；`int(text)` 后调用对应 Data constructor，输出再 `str(int)` |
| Null / Boolean | null / boolean | 标签和值严格对应，不把 null 当失败值 |
| Float32/Float64 | 十进制文本 | 只在该标签下转换 IEEE 数值；限制有限值/范围，保留原始编码供诊断 |
| OctetString / BitString | HEX 字节对 / 01 字符串 | 字节对校验、位数由字符串长度保留；限制总字节/嵌套深度/元素数 |
| VisibleString / Utf8String | string | 按相应字符集和编码长度检查 |
| Date/Time/DateTime/DateTimeS | ISO 本地日期/时间文本 | 当前 UI 是有效日历字段子集；协议日期无时区，不自动按浏览器 UTC 转换 |
| Array/Structure | `Dlt698Data[]` | 逐项类型和结构校验，保留顺序、长度和标签，空集合与 Null 有区别 |

64 位原始值全链路都使用整数/十进制字符串：`UInt64("18446744073709551615")` 不经过 JS Number、Python float、SQL FLOAT 或 IEEE 近似工程值。工程值优先使用 `standard.engineering_values` 与 `decimal_text`；例如 `00100401` 倍率 -4 得到 `1844674407370955.1615`。普通工程整数亦精确保留（2301 → 230.1 V、5000 → 5.000 A）。

**契约扩展门槛：**库提供的 Data 标签比当前前端的类型子集更完整，日期还保留星期/毫秒/未指定等原始字段。后续增加 `raw_fields`/`encoded_hex` 或带 tag 的 RawData 变体后，才开放这些编辑/写入能力。当前遇到无法无损表达的值，保留真实报文及原始类型诊断，返回 validation_error/明确不支持；不得伪装成 Null、字符串或“完整支持全部标签”。普通读到标准类型不符时，应返回收到的可表达 Data 和验证错误。

## 5. 运行时与会话

### 5.1 统一所有者和单会话单请求

建议新增 `src/proto/dlt698/runtime.py`、`codec_adapter.py`、`catalog.py`、`records.py`、`capabilities.py`，以及 `src/data/service/dlt698_service.py`。每个通道仅由一个 runtime owner 管理；HTTP 处理器和 UI 不另行打开相同端点。

常规客户端使用 `AsyncClient`，服务端只读发布使用 `AsyncServer`。这两个入口要求所属 loop/thread；覆盖现有 `ProtocolHandler.read_value_async/write_value_async`，不能把原生异步对象传入任意 `asyncio.to_thread`。专家功能使用显式驱动的 Engine/Endpoint 与 registry/provider，轮询 budget 和队列限制统一配置。不要通过访问 `AsyncServer._server` 等私有字段假装拿到了可控专家会话。

每个 session 建立请求队列/锁，普通读、探测、记录、SET、ACTION、MD5、ThenGet、PROXY、自动读取共用；一次最多一个主动事务，记录 GET Next 链占用同一槽位直到收齐。任务使用会话 generation + token 关联响应，避免重连后旧结果更新新会话。网络事件/上报回调只复制或投递，不在回调内阻塞读取同一 runtime。

自动读取复用 `AutoReadTaskManager`，按周期执行，上一周期未完成时不叠加新任务；人工操作与自动周期经同一仲裁，停止后等待在途事务退出，状态为 stopping 直到真正结束。READ 可以按明确策略再次人工发起；**SET/ACTION/其代理及 ThenGet 不自动重试、不回滚**。

前端 AbortSignal 只取消 HTTP 等待，不证明 native 已停止、也不证明远端未执行。后端处理连接断开时必须定义任务取消策略：读请求取消并清理；写请求若已发送，审计为 `unknown`，保留 operation_id；新会话建立前等待 native cancel/close 排空。后续增加显式任务查询/取消 API，见 7.4。

`AsyncClient._wait` 遇超时/取消会清除关联并调用 Engine.cancel；应用必须据此更新状态和重建流程，不能继续宣称 associated。启动/停止和应用关闭等待 `aclose()`，清理定时器、pending futures、会话路由和模拟任务。配置重载遵循已有设备替换生命周期：校验→持久化→停旧实例→启新实例；失败返回恢复结果，不能留下两个监听器。

### 5.2 角色、方向、关联与协商

`conn_type` 表示传输方向/串口入口，`Dlt698Config.role` 表示主站/client 或表计/server。一期默认对应 0/1 为 client、2/3 为 server。需要主站监听或表计主动拨号时使用 `Engine.connect_tcp/listen(role=...)`，同时调整公共 helper 的“is_client”判断，不能只从 TCP 方向推断协议角色。

| 前端参数 | 库映射 |
| --- | --- |
| server_address / logical_address | `ServerAddress(bytes=bytes.fromhex(...), logical=..., type=AddressType.single)` |
| client_address / request_timeout_ms / heartbeat_interval_s | `SessionOptions.client_address / request_timeout(ms/1000) / heartbeat_seconds` |
| protocol_version | `AssociationParameters.version` |
| send_frame_max / receive_frame_max / receive_window | `send_frame_bytes / receive_frame_bytes / receive_window` |
| apdu_max / association_timeout_s | `apdu_bytes / timeout_seconds` |
| association=public | TCP 常规入口 `ConnectionProfile.remote_public`；串口公共入口 `local_public`，按库入口验证完整 LINK/CONNECT |
| association=preestablished | 映射库实际 `ConnectionProfile.local_preset`；不构造不存在的 remote_preestablished 枚举，所选传输/角色不适用时明确拒绝 |

`SessionOptions` 和布局再经库 validator 校验。前端数值范围只是基础约束，不代替 native 限制。串口默认 9600、8E1；使用 configured 入口构造 SerialOptions/SerialLinkOptions，字格式与 bits_per_character 一致，高层不开放 1.5 停止位。RS-485 手动方向与排空需真实 hooks；未配置不显示硬件接入成功。

运行状态区分 stopped、listening、associating、associated、requesting、timeout、rejected、cancelled、lost。监听成功不等于已有已关联主站；端口 0 返回真实 local_port。状态需分别暴露本地 requested 配置、协商 negotiated 结果及服务/业务位（当前类型缺后两组位，后续加字段）；帧长度不含起止字节，APDU 长度不含链路封装。

### 5.3 Capability 门控

`status.available` 表示 EMS 后端运行时可用，`features[x].supported` 表示本通道/角色/当前 provider 的应用能力；未协商的远端服务能力保持 unknown，不能由“标准目录有这个对象”推断设备支持。需要区分应用可提供该功能与远端已知是否支持 List。

`points/config/import` 可在设备停止时提供；get/set/action/records/reports/proxy/routes/local_values/auto_read/mapping/simulation/history/md5/then_get 由实际适配进度、角色、关联和 provider 决定。未实现必须 `supported=false` 且具体 reason。路由/报告/高级认证不能因存在枚举或页面就返回 true。

## 6. 协议业务实施

### 6.1 普通对象、List 和探测

使用 `capabilities/service_support/plan_reads` 规划读取。远端 List 支持未知时采用 Normal；明确支持 List 才按 APDU 限制分批。标准候选项默认保留未知对象；catalog 仅生成点定义，probe 才显式发起 GET。同步 Client 没有同等高层 probe_points/capabilities 入口，一期用 AsyncClient。

请求和响应均按 index 对齐，保留重复项，例如 `[A,B,A]` 必须返回 3 项；禁止转成 `{oad: result}` 字典、set 或按 OAD 去重。响应项数/地址/顺序不符应记录协议异常并填对应错误，不把最后一项复制给所有重复项。Data、远端 DAR、transport_error、validation_error 分开输出，HTTP 200 仅说明请求已得到逐项结果，不表示每项成功。

SET/ACTION 调用库 `set/set_list/action/action_list`，权限来自目录 schema/provider；ACTION 保留 DAR 和可选返回 Data（即使 DAR 成功也不伪造 Data）。当前结果模型中 SET 的 DAR=0 仍为 `kind=dar,dar=0`，ACTION 同样保留 dar 并可同时携带 data；页面必须把 DAR=0 显示为成功，不将所有 kind=dar 一概视为失败。发出后超时/取消标记 unknown；重新读取是独立 GET，不能作为写操作自动重试。标准电能不附带 DLT645 清零、密码写入或广播校时。

### 6.2 本地发布值、目录与权限

Server/AsyncServer.set 和 Device.set/set_element 是本地值发布，不授予远端 SET，不自动注册 ACTION/记录。服务端本地 `local_values` 验证 Data 后发布完整属性或显式元素。Array 元素索引为 1-based，更新元素须保持数组长度/布局，原子发布后统一更新点快照。

远端可写属性与方法另建 `ObjectRegistry`、`AttributeSchema`、`MethodSchema`、`MemoryObject.bind_method/bind_record`，由 attach_services 驱动。方法仅绑定已实现 provider，不能把 UI 的自定义 OMD 自动执行为 Python 代码或模拟成功。没有 provider 的自定义方法显示未绑定。

### 6.3 记录与 GET Next

四类模板限定日冻结、月冻结、掉电、初始化；OAD/默认列取 `standard.find_record`。UI 的 all/at/between/sequences/latest 分别映射 SelectAll、record_at、record_between、record_sequences、`Selector9(previous=latest)` + make_record_query。latest 是最近第 n 次，不能解释为最近 n 行。

时间与序号范围按 `[start,end)`，校验 start<end；序号按整数转换而非 float。标准记录使用 NULL 区间间隔；MemoryRecords 当前仅有 RSD 0/1/2/9。ROAD、MS 和其他 RSD 线上模型/codec 存在不代表已有业务 provider；无 provider 时禁用，普通 GET 不用作记录的降级路径。

结果表头来自 `RecordResult.columns`（真实 RCSD），保持列顺序与重复列，不拿请求列假装响应列；0 行成功也返回真实 columns。DAR 与成功空数据分开。标准列验证失败保留原响应及诊断。当前前端 columns 只能表达 OAD，故 ROAD 必须先扩展契约后开放。

库 get_record/get_record_list 已由原生状态机收齐 GET Next。应用保持同一会话锁并从真实 traffic/completion 统计块号、累计行数和块数，不能以浏览器分页页数作为 blocks。不能统计真实块数时扩展类型为 unknown，而不是填虚构值。设置总响应字节/行数/时限上限，超限返回明确诊断并清理 native 事务。

本地新增记录：校验 query 与每列 Data，数据库事务追加；生成有序完整快照，再调用 `MemoryRecords.replace_rows`。当前库没有 append API，不调用不存在的 append。数据持久化与发布失败需记录一致性状态并支持重新发布；记录不自动定期冻结或检测事件。本地管理查询不额外发网络 GET。

### 6.4 REPORT、FollowReport 与 ACD

客户端专家 session 注册 `set_report_handler`、`set_follow_handler`、`set_acd_handler`，保留来源会话、PIID-ACD、完整普通/列表/记录/透明 payload 和确认状态。REPORT handler 返回值用于确认；队列溢出/失败策略明确记录 dropped count，不能确认成功后静默丢弃业务数据。FollowReport 和 ACD 不是普通 GET 的成功 Data 替代物。

服务端主动 REPORT 只针对当前已关联且属于当前通道的会话，通过 Engine.exchange/SessionHandle.async_exchange 处理原生确认、次数和超时。REPORT 机制重试与 SET/ACTION 业务重试严格分开；未接专家 runtime 或无可用会话时拒绝发送。

当前 `Dlt698Report` 每行仅一个 OAD/Data，足够显示普通上报，但完整列表/记录/透明上报需要新增 variant/items/record/trans/raw envelope；PIID-ACD 不能只存格式化文字后丢掉控制位。能力标记仅开放已无损接入的分支。

### 6.5 PROXY、路由与高级请求

七类服务对应普通读列表、记录、写列表、写后读、方法列表、方法后读、透明传输。客户端使用高级 exchange，逐 TSA、逐请求项按原顺序保留重复目标和部分失败。前端已经补齐 `options` 专用参数表单：记录查询放入 `options.query`，ThenGet 每项包括 `get_oad/delay_s`，方法使用 `omd`。透明传输由 `options.port`（OAD）、`bytes`、`response_timeout_s`、`byte_timeout_ms` 和 `communication` 构成，不要求额外 TSA；通信配置含 `baud_rate/data_bits/stop_bits/parity/flow_control`，后端须映射到原生 COMDCB 编码后再校验。不能将 JSON 参数直接透传为原生对象，不能给缺参数请求编造默认成功。

`ProxyRouter.bind(Tsa,SessionHandle)` 只绑定同一 owner 管理的已关联目标，持续 poll 所有相关会话；路由保存仅接受服务器可验证的 session_id，拒绝别的通道或已失效 session。会话断开/代次变化立即解绑，重新关联后按明确目标配置重新绑定。

`TransBridge` 是 drain/complete 任务交付机制，不是真实串口转发器。应用另接实际端口后端，控制目标/端口许可、字节预算、超时、任务取消和错误映射。UI 传入 bridge 字段只作显示占位，连接状态一律后端派生；无 bridge 后端仅返回 unavailable，不允许浏览器声称 connected。

MD5、SET/ACTION ThenGet 使用 AsyncClient.exchange 或专家 exchange，保留完整响应；写后读中写项/读项分别输出，不用读成功掩盖写结果未知。固定单一接口角色和 payload 的 discriminated union 后才打开 capability。

### 6.6 安全

默认公共连接；预设关联不等于认证成功。SecurityBackend 无内置真实密码算法/ESAM，配置具体后端才开启密码/对称/签名机制。每个 session 的 backend 实例独立，使用 `security_backend_factory` 生成；凭证只保存安全引用，不写报文日志或普通配置响应。

当前 Python SecurityBackend 子类只能配置在调用线程驱动的 Engine/AsyncClient；托管同步 Client/Server 拒绝此后端，AsyncServer 包装同样受限制。需要 Python 安全后端的服务端必须走专家 Engine 生命周期并通过真实认证验收。公共 TLS 存储可复用端点配置习惯，但不能将 TLS 验证等同于 DL/T 698 应用认证。

## 7. HTTP 接口契约

### 7.1 统一前缀、错误与 ID

专属前缀 `/api/dlt698/channels/{channel_id}`；成功响应 `{ "code": 200, "message": "...", "data": ... }`。前端适配暂兼容 0 和 200，后端只采用已有 200 约定。通道不存在返回 404；非 8 返回协议不符；格式/权限/范围错误返回 422/403；会话忙或配置冲突返回 409；运行时未安装或未接入返回 503。远端 DAR 和每项传输/验证错误放在成功 envelope 的结果项，不误用 HTTP 500。

每个入口查询真实 channel/device 并验证协议、角色、会话归属和 capability，不能仅凭 URL 或请求角色执行。低层异常通过明确 serializer 转换，不让 `BaseResponse` 的兜底 str(native object) 替代 typed Data。

### 7.2 与当前前端一一对应的接口

下表为后续实现路由，不表示当前后端已有。

| HTTP / 路径（相对前缀） | 请求体 | `data` 响应 | 业务约束 |
| --- | --- | --- | --- |
| GET `status` | 无 | Dlt698Status | 停止时也可查询；含 capability/reason、sessions、negotiated、auto_read、security_backend |
| GET `config` | 无 | Dlt698Config | 返回持久化 requested 配置和 defaults，不伪造协商值 |
| PUT `config` | Dlt698Config | Dlt698Config | 复用 ChannelConfigurationService；配置版本/停止重载受控 |
| GET `points` | 无 | Dlt698Point[] | 返回定义 + 原始结果 + last_good；无在线值时不默认成功 |
| POST `points` | Dlt698Point | Dlt698Point | 忽略/拒绝客户端提交的 result/last_good；校验目录及 code 唯一 |
| PUT `points/{original_code}` | Dlt698Point | Dlt698Point | code URL 解码后精确匹配；重命名同步引用 |
| DELETE `points/{code}` | 无 | null | 清理定义及引用/运行状态，不能仅删缓存 |
| POST `catalog` | `{wiring,tariff_count,harmonic_order}` | Dlt698Point[] | 返回候选定义，不自动安装/在线验证，也不设 last_good |
| POST `read` | `{codes:string[]}` | Dlt698Result[] | 至少一项；按 input index 返回，重复 code 保留 |
| POST `probe` | `{oads:string[]}` | Dlt698Result[] | 显式线上 GET；重复 OAD 保留，不保存候选成功为全局能力 |
| POST `operations` | Dlt698Operation | Dlt698Result[] | 分别路由 set/action/local_values/report/proxy/md5/then_get，能力与参数完整性校验 |
| POST `records/query` | Dlt698RecordQuery | Dlt698RecordResult | client 线上记录；server 本地存储查询；真实响应列、空行/原始 DAR |
| POST `records/rows` | `{query:Dlt698RecordQuery,row:Dlt698Data[]}` | null | server、本地持久化和快照替换；row 长度与 schema 一致 |
| GET `reports` | 无 | Dlt698Report[] | 有界近期数据；未接收不填示例报告；后续加游标/variant |
| GET `routes` | 无 | Dlt698Route[] | runtime session 与 bridge 状态真实派生 |
| POST `routes` | Dlt698Route | null | 验证 TSA、同通道已关联 session；bridge 输入不授予权限 |
| PUT `auto-read` | `{running,interval_ms,codes}` | null | 启停同一公共后台任务；interval 范围、code 列表及当前角色验证 |
| POST `points/import` | multipart `file` | `{count:number}` | 验证后整批事务导入；CSV/JSON 或 XLSX 支持格式明确声明，不能靠文件名猜类型 |

PUT config 与现有通道 `protocol_params.values` 统一来源，不产生两份独立配置。import 必须支持 UTF-8 中文名称、字符串整数、重复 code 错误清单、文件/行/字节上限；catalog 类型值的初值按 native 默认校验生成，不宣称模拟物理测量。

### 7.3 具体 payload

配置示例（TCP/串口端点仍通过现有设备表单提交，不重复在该 body 内维护）：

```json
{
  "role": "client", "server_address": "000000000001", "logical_address": 0,
  "client_address": 16, "association": "public", "request_timeout_ms": 5000,
  "heartbeat_interval_s": 30, "protocol_version": 1,
  "send_frame_max": 2048, "receive_frame_max": 2048, "receive_window": 1,
  "apdu_max": 2048, "association_timeout_s": 120,
  "wiring": "three_phase_four_wire", "tariff_count": 4, "harmonic_order": 21
}
```

有序读取及重复项：

```json
{ "codes": ["A_VOLTAGE", "FREQUENCY", "A_VOLTAGE"] }
```

```json
{
  "code": 200, "message": "读取完成",
  "data": [
    { "index": 0, "oad": "20000201", "kind": "data", "data": { "type": "UInt16", "value": "2301" }, "updated_at": "2026-10-13T02:24:08Z" },
    { "index": 1, "oad": "200F0200", "kind": "dar", "dar": 4, "message": "远端返回 DAR=4" },
    { "index": 2, "oad": "20000201", "kind": "transport_error", "message": "请求超时，保留上次成功值" }
  ]
}
```

SET 与 ACTION 分别按对应地址解释，不能把 OMD 当 OAD 属性读写：

```json
{ "service": "set", "items": [{ "oad": "F0010200", "data": { "type": "UInt64", "value": "18446744073709551615" } }] }
```

```json
{ "service": "action", "items": [{ "omd": "F0010100", "data": { "type": "Structure", "value": [{ "type": "Enum", "value": "1" }, { "type": "Null", "value": null }] } }] }
```

当前 `Dlt698Result.oad` 也用于操作表的 `OAD / OMD` 显示，兼容期 ACTION 返回时该字段回显 OMD；正式服务扩展 `omd/address_kind`，避免名字误导。结果未知示例：

```json
{ "code": 200, "message": "操作已结束", "data": [{ "index": 0, "oad": "F0010200", "kind": "unknown", "message": "写入已发送但未收到响应，执行结果未知；可独立重新读取核实" }] }
```

记录查询示例（请求列仅为示例，后端必须通过模板和 native schema 校验）：

```json
{
  "template": "daily", "oad": "50040200", "selector": "between",
  "start": "2026-10-01T00:00:00", "end": "2026-10-13T00:00:00",
  "latest": 1, "columns": ["20210200", "00100201"]
}
```

空查询成功仍保留真实表头；示例 blocks 仅用于展示响应结构，实施须读取实际统计：

```json
{ "code": 200, "message": "查询成功，无匹配记录", "data": { "columns": [{ "oad": "20210200", "name": "冻结时间" }, { "oad": "00100201", "name": "正向有功总电能" }], "rows": [], "blocks": 1 } }
```

服务端普通上报与路由意图：

```json
{ "service": "report", "session_id": "runtime-session-1", "options": { "report_kind": "normal" }, "items": [{ "oad": "20000201", "data": { "type": "UInt16", "value": "2301" } }] }
```

```json
{ "tsa": "000000000001", "session_id": "runtime-session-2", "bridge": "unavailable" }
```

### 7.4 上线前必须补齐的契约

REPORT 表单已提供 `options.report_kind=normal/list/record/transparent`。normal/list 使用有序 `items[{oad,data}]`；record 使用 `options.record={oad,columns,rows}`；transparent 使用 `options.port` 和 `frames`（逐帧 HEX 字节串），不伪造普通属性 Data。接收契约可保留 `items/record/port/frames/follow_report/acd`，详情窗口展示完整原始 JSON；后端须提供真实 PIID-ACD 和确认状态，不能从发送按钮推断成功。

现有前端覆盖基础工作区，并增加服务专用 `options`、逐项 `get_oad/delay_s`、嵌套结果 `tsa/children/md5`；以下能力仍需与 Pydantic schema、原生适配和 API 一起验收后才开启 feature：

| 扩展 | 具体内容 | 触发阶段 |
| --- | --- | --- |
| 原始 Data | 原始日期字段/全部 native tag/encoded_hex 的无损 variant；限制和只读详情 | 非子集数据和完整诊断上线前 |
| 能力/协商 | requested 与 negotiated、protocol/function 位、transport 端点/实际端口、远端服务 unknown/yes/no | 真实关联上线前 |
| 操作审计 | operation_id、会话 generation、sent/completed/unknown；GET `operations/{id}`；POST `operations/{id}/cancel` | 长任务、取消和写操作恢复上线前 |
| 分页/进度 | records query task_id、GET Next block/byte/row progress；HTTP 同步接口有总预算 | 长记录上线前 |
| 记录列 | CSD OAD/ROAD discriminated union、列定义与修改、替换记录接口；当前只开放 OAD | 自定义记录或替换功能上线前 |
| REPORT | normal/list/record/trans envelope、PIID-ACD 原值、确认枚举、游标和方向 | 非普通报告上线前 |
| PROXY | 前端已有七类专用参数和有序请求项、逐 TSA 嵌套结果；后端以 service 判别联合强校验 options，并转换 COMDCB | 七类服务逐项接入前 |
| ThenGet | 前端以 options.operation 区分 set/action，每项独立 oad/omd、get_oad、delay_s；后端保留每段结果 | then_get 入口开放前 |
| 安全配置 | 后端标识、认证机制、凭证引用、失败原因、脱敏响应；不能只加密码输入框 | 具体 SecurityBackend 接入前 |

HTTP client 当前固定 15s timeout，而协议请求允许更长时限、批量 Normal 和 GET Next 也可能超时；上线时统一预算，简单请求限制在 HTTP 总预算内，较长操作采用任务接口。仅提高前端 timeout 不能解决取消/重连/结果未知语义。

## 8. 公共能力复用

| 公共入口 | 复用方式 | DLT698 适配边界 |
| --- | --- | --- |
| 新建/编辑设备及连接配置 | 原有通道表单和 `protocol_params.values` | 协议专属 SA/CA/关联/协商字段；独立角色不被 TCP 方向覆盖 |
| 启停设备/设备信息 | 原设备 API 与 controller | handler 统一生命周期和状态；监听与关联数独立 |
| 客户端连接监控 | `ServerHandler` / connection_registry / 现有当前与历史接口 | 将 native connection + generation 映射到稳定 session_id，更新关联与真实断开原因 |
| 查看报文 | MessageCapture / MessageParser / 公共消息接口 | 增加 `parsers/dlt698.py`，用 codec/protocol 解链路/APDU；原始字节、时间、方向、会话、错误和丢弃数真实记录 |
| 测点属性/映射 | PointMappingService、现有详情控件 | 映射只接可表达精确数值的标量，Decimal/整数运算并校验目标类型/范围；复合值不交给 float evaluator |
| 数据模拟/批量模拟 | simulation_controller / point_simulator 与公共弹窗 | server 本地发布；client 不支持；仅开启已有安全适配的标量类型/步长/范围，Array/Structure 要显式完整 Data 策略 |
| 变化回溯 | 既有来源/事件路径 | 事件携带完整 typed Data 和来源；大值不串行化为 float；客户端超时不产生值变化记录 |
| 自动读取 | AutoReadTaskManager 及原设备状态入口 | 专属 `/auto-read` 作为同一服务的适配；单会话锁、重复项、last_good |

映射、模拟、回溯页面在 capability 尚未支持时保留禁用原因，不从前端草稿宣称已持久化。复用公共 UI 时先落实 typed adapter 再启用按钮，避免把数值 18446744073709551615 送入既有 float 表单链路。

## 9. 实施阶段与验收

### P0：契约、依赖和禁用状态

- 锁定库源码提交/版本、Python ABI、Windows/Linux wheel，补包构建与启动 smoke；安装失败不影响已有协议启动。
- 实现协议 8 防回退、status/config 基础路由、capability reasons、Pydantic 严格字段与 typed serializer；完成 7.4 的基础协商/审计扩展设计。
- 验收：后端未安装时 8 不进入 Modbus；现有 0～7 API 和已保存通道保持行为；界面准确显示未接入。

### P1：持久化、目录与基础回环

- 完成 SQLite/MySQL 模型/迁移、CRUD/import/catalog、复制/删除/重载；实现 typed Point 与公共设备适配。
- AsyncClient/AsyncServer 完成 TCP、配置串口、LINK/CONNECT、普通 GET 和服务端本地发布；接报文及当前/历史连接。
- 验收：本机两个端点回环读取 UInt16、UInt64 极值、Array/Structure；标准倍率正确；断线保留 last_good；监听 port=0 真实端口正确；重新启动无遗留端口/任务。串口硬件测试单列，不能用 TCP 回环代替。

### P2：List、自动读取、SET/ACTION

- 实现单会话仲裁、能力规划、ordered results、探测；复用自动读取生命周期；注册明确 provider/schema 后开放远端 SET/ACTION。
- 验收：`[A,B,A]` 返回三项；List 部分 DAR、不匹配响应、标准类型失败保留原 Data；人工读/自动读/写同时触发时实际并发事务数为 1；停止等待在途结束；写已发后超时/取消结果 unknown，网络抓包确认没有自动重试/回滚。

### P3：记录与公共数值功能

- 四类模板、本地记录持久化/replace_rows、真实 RCSD、原生 GET Next 收齐和进度；完成模拟/映射/回溯的精确数值适配。
- 验收：`[start,end)` 边界、latest 第 n 次、序号范围、0 行带表头、DAR 与空成功、响应列与请求列不同、多块收齐、取消/超限清理；无 provider 的 ROAD/MS/RSD 禁用；模拟/映射越界拒绝，Int64/UInt64 不失真。

### P4：专家报告与高级服务

- 接统一专家 runtime、REPORT/Follow/ACD、逐 TSA 代理、路由代次、MD5/ThenGet；每个 service variant 通过测试才启用 capability。
- 验收：不同 session 上报来源/PIID-ACD/确认准确，部分失败和重复 TSA 保留；断开路由立刻不可用；透明桥无真实后端时 unavailable；重试仅限规定的协议分片/报告机制；高级请求参数缺失明确拒绝。

### P5：真实设备、安全与发布

- 测试真实设备 Normal/List 能力差异、串口/RS-485 时序、目标桥接和选定 SecurityBackend；补 wheel/PyInstaller/应用关闭兼容。
- 验收：真实关联协商、密码/对称/签名仅开放验收过的机制、每 session backend 独立、日志脱敏、无晚到回调；明确记录支持设备/角色/传输矩阵和未接入项后发布稳定版本。协议 8 可在核心回环验收后先发布基础能力，高级 feature 逐阶段开放。

每阶段提交接口契约、实现、对应回环/异常/迁移测试和验收记录；未通过能力保持 false。建议测试路径 `tests/protocols/dlt698/`、`tests/web/api/test_dlt698.py`、`tests/data/test_dlt698_migration.py`。现阶段只交付本计划，不执行这些尚不存在的后端测试，也不将设计预览当作协议验收。

## 10. 核对结论与已知限制

当前 Python 库已经提供普通/列表读写、记录、标准目录、精确 Data、异步探测和专家服务入口，但 EMS 后端尚无 DL/T 698 依赖、处理器、模型或路由。实施重点是 owner 生命周期、typed Data 持久化、单会话仲裁及能力门控，不能只增加路由后调用 DLT645 的值链路。

已核对并特别限定：ConnectionProfile 实际仅 remote_public/local_public/local_preset；MemoryRecords 当前只有 replace_rows；高层 Device 为只读本地发布；高级报告/路由需要专家 session；Python 安全后端不适用于托管 Server；当前 Data 子集尚不能无损覆盖全部原生标签、完整 ROAD 和任务取消。高级服务表单与 options 已具备，但仍需后端判别联合和原生服务验收。以上约束在对应能力接入前必须落实。
