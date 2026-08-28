# DNP3 协议接入设计文档

> 协议：DNP3（Distributed Network Protocol 3 / IEEE 1815）
> 定位：北美电力 SCADA 通信协议（北美版 IEC 104）
> 状态：设计阶段
> 参照：本设计严格对齐现有 Modbus / IEC 104 / DL/T 645 / IEC 61850 的接入架构（后端 `ProtocolHandler` 体系、报文解析器、前端协议表单与测点体系）

---

## 1. 目标

为 EMS Simulate 增加 **DNP3** 协议支持，可模拟 DNP3 **Outstation（从站/服务端）** 与 **Master（主站/客户端）** 两种角色，接口与现有四大协议保持一致。

验收要求：

- 服务端可模拟 DNP3 Outstation，响应 Master 的完整性轮询（Class 0/1/2/3）、读请求、时间同步与 SBO/DO 控制操作；
- 客户端可作为 Master，对真实 Outstation 执行完整性轮询、读取测点、下发控制与设定值、时间同步；
- 测点体系沿用 YC/YX/YK/YT 四遥模型，通过对象组/变体映射到 DNP3 对象；
- 报文查看器可实时捕获并解析 DNP3 链路层/传输层/应用层报文；
- 前端协议表单、测点配置、报文查看、模拟配置等与其它协议体验一致；
- 支持 TCP（默认端口 20000）与串口两种物理链路（第一版先 TCP）。

## 2. DNP3 协议要点

DNP3 是北美电网广泛使用的 SCADA 通信协议（IEEE 1815），与 IEC 60870-5-104 地位对等，二者均源自 IEC 870-5。协议分三层：

### 2.1 分层结构

| 层 | 作用 | 说明 |
| --- | --- | --- |
| 数据链路层（Data Link） | 帧定界、差错校验、链路确认 | 帧头 `0x0564` + 长度 + 控制字 + 目的/源地址 + 数据块（每 16 字节带 2 字节 CRC） |
| 传输层（Transport） | 报文分片/重组（≤250 字节/片） | TPDU 头（TH/TL 两位序号 + FIN/FIR）+ 应用层数据 |
| 应用层（Application） | 请求/响应语义、对象读写 | APDU：应用控制字 + 功能码 + 对象头 + 对象数据 |

### 2.2 链路层帧格式

```
┌────────┬────────┬────────┬─────────┬─────────┬──────────────┬──────┐
│ 0x0564 │ LENGTH │ CTRL   │ DST_ADDR│ SRC_ADDR│ DATA (≤250B) │ CRC  │
│ 2 字节 │ 1 字节 │ 1 字节 │ 1/2字节 │ 1/2字节 │ 每16字节一块  │ 2字节 │
└────────┴────────┴────────┴─────────┴─────────┴──────────────┴──────┘
```

- 起始字固定 `0x05 0x64`；
- 长度 = 控制字 + 地址 + 数据（不含起始字与 CRC）；
- 控制字含 DIR/PRM/FCB/FCV/功能码（链路层确认、请求/响应等）；
- 地址支持 1 字节或 2 字节（由两端配置一致决定）；
- CRC 采用 DNP3 专用 CRC（多项式 0x3D65，初值 0）。

### 2.3 应用层功能码

| 功能码 | 名称 | 用途 |
| --- | --- | --- |
| 0 | Confirm | 确认（应用层/事件确认） |
| 1 | Read | 读对象（如 G60V1 读取 Class 数据） |
| 2 | Write | 写对象（时间同步等） |
| 3 | Select | 选择（SBO 第一步） |
| 4 | Operate | 执行（SBO 第二步） |
| 5 | Direct Operate | 直接执行（DO） |
| 6 | Direct Operate, No Ack | 直接执行不确认 |
| 20/21 | Enable/Disable Unsolicited | 使能/禁止未请求上报 |
| 22 | Assign Class | 分配事件类（Class 1/2/3） |
| 23 | Delay Measure | 链路延迟测量 |
| 129+ | 响应 | 响应码（0 成功、1 不支持、2 无对象、…、8 对象不匹配等） |

### 2.4 对象组（Group）与变体（Variation）

DNP3 以"对象组 + 变体"组织数据，本系统按四遥模型映射：

| 对象组 | 名称 | 四遥映射 | 说明 |
| --- | --- | --- | --- |
| G1 / G2 | Binary Input（BI）/ BI Event | **YX 遥信** | 开关、告警状态（静态/事件） |
| G10 / G12 | Binary Output（BO）/ BO Event | **YK 遥控** | 控制输出（SBO/DO） |
| G20 / G22 | Counter / Counter Event | （扩展） | 累加量（电量等） |
| G30 / G32 | Analog Input（AI）/ AI Event | **YC 遥测** | 模拟量（含死区事件） |
| G40 | Analog Output（AO） | **YT 遥调** | 设定值（SBO/DO） |
| G50 | Time and Date | 时间同步 | 绝对时间（UTC，毫秒精度） |
| G60 | Class Objects | 轮询 | Class 0/1/2/3 数据类 |
| G80 | Internal Indications（IIN） | 内部指示 | 状态/错误标志 |

变体（Variations）决定编码格式：如 G30V1（32-bit）、G30V2（16-bit）、G30V5（32-bit + 品质）、G30V6（16-bit + 品质）、G1V1（单比特）、G1V2（带品质）等。第一版支持常用变体：G1V1/V2、G30V1/V2/V5/V6、G10V2（控制码）、G40V1/V2、G50V1、G60V1-V4。

### 2.5 类（Class）与轮询模型

- **Class 0**：全部静态数据（完整性轮询 Integrity Poll 读 G60V1）；
- **Class 1/2/3**：事件数据（事件类，可分配不同优先级）；
- Master 周期性执行完整性轮询 + 事件轮询；Outstation 维护静态值缓存与事件缓冲（事件超限可触发未请求上报）。

### 2.6 控制操作模型

- **SBO（Select-Before-Operate）**：先 Select（功能码 3），Outstation 返回选择成功并锁定对象，再 Operate（功能码 4）执行；
- **DO（Direct Operate）**：功能码 5 一步执行；
- 控制码（Control Code）含 CTO（清除/保持/脉冲）与时序选项（Trip/Close、Pulse On/Off、Latch 等）；本系统第一版支持 **Trip/Close、Latch On/Off、Pulse On/Off**，与现有 YK 遥控的 command_type 对齐。

### 2.7 未请求响应（Unsolicited）

Outstation 可配置 Enable Unsolicited（功能码 20），当事件发生时主动上送（带应用层确认）。第一版服务端支持未请求响应（默认关闭，可由参数开启）；客户端支持使能/禁止未请求。

## 3. 整体架构

与现有协议完全对齐，接入点如下：

```
┌─────────────── 前端（Vue3） ───────────────┐
│ 协议类型常量 / 默认端口 / 协议参数表单      │
│ 测点配置（对象组/变体、索引、死区、事件类） │
│ 报文查看（DNP3 解析器）                    │
└──────────────────┬─────────────────────────┘
                   │ REST API
┌──────────────────▼─────────────────────────┐
│ 通道 API / 数据库（protocol_type=5）       │
│ Device / GeneralDeviceBuilder              │
│ ProtocolHandler 体系（src/device/protocol）│
│   DNP3ServerHandler / DNP3ClientHandler    │
│   │                                        │
│   ▼                                        │
│ src/proto/dnp3/（pydnp3 封装）             │
│   dnp3_server.py（Outstation）             │
│   dnp3_client.py（Master）                 │
│   log.py / tls.py（可选）                  │
│   │                                        │
│   ▼                                        │
│ src/device/core/message/parsers/dnp3.py    │
│   （报文解析：链路/传输/应用层）           │
└────────────────────────────────────────────┘
```

## 4. 后端设计

### 4.1 枚举与常量

`src/enums/modbus_def.py` 的 `ProtocolType` 增加：

```python
Dnp3Server = "Dnp3Server"   # DNP3 服务端（Outstation）
Dnp3Client = "Dnp3Client"   # DNP3 客户端（Master）
```

通道 `protocol_type` 数值约定 **5**（与前端 `PROTOCOL_TYPE` 对齐）：0=ModbusRTU、1=ModbusTCP、2=IEC104、3=DLT645、4=IEC61850、**5=DNP3**。

### 4.2 协议库选型：pydnp3

采用成熟开源库 **pydnp3**（opendnp3 的官方 Python 绑定，Automatak），与项目"封装成熟库"的风格一致（pymodbus / c104 / dlt645 / pyiec61850-ng）：

- 同时提供 **Outstation** 与 **Master** 两套完整实现（含 TLS、时间同步、未请求、事件缓冲）；
- 跨平台（Windows / Linux），有 PyPI wheel；
- 依赖 `pydnp3>=0.x`，加入 `pyproject.toml`（含 Windows/Linux 离线 wheel 构建，参照 c104 处理方式）。

### 4.3 `src/proto/dnp3/` 模块

```text
src/proto/dnp3/
├── __init__.py
├── dnp3_server.py     # Dnp3Server（Outstation 封装）
├── dnp3_client.py     # Dnp3Client（Master 封装）
├── log.py             # 报文回调 → 捕获器
└── tls.py             # TLS 配置构建（第一版可选）
```

**Dnp3Server（Outstation）核心接口**（对齐 `iec104server.py` 风格）：

```python
class Dnp3Server:
    def __init__(self, log=None): ...

    def set_addresses(self, local_addr: int, remote_addr: int) -> None: ...
    def set_serial_config(self, port, baudrate=9600, bytesize=8, parity="N", stopbits=1) -> None: ...
    def set_server_port(self, port: int) -> None: ...       # TCP 20000
    def set_parameters(self, **kwargs) -> None: ...          # 时间同步、未请求、事件缓冲等

    def add_binary_input(self, index: int, point_code: str, deadband: int = 0) -> None: ...
    def add_analog_input(self, index: int, point_code: str, deadband: float = 0.0) -> None: ...
    def add_binary_output(self, index: int, point_code: str) -> None: ...
    def add_analog_output(self, index: int, point_code: str) -> None: ...

    def start(self) -> bool: ...
    def stop(self) -> bool: ...
    def isRunning(self) -> bool: ...

    # 值与事件
    def get_point_value(self, index: int, frame_type: int = 0) -> Any: ...
    def set_point_value(self, index: int, value, frame_type: int = 0) -> None: ...
    def set_point_quality(self, index: int, quality: int, frame_type: int = 0) -> None: ...
    def set_on_command_callback(self, callback) -> None: ...  # 遥控/遥调回调
```

**Dnp3Client（Master）核心接口**：

```python
class Dnp3Client:
    def __init__(self, log=None): ...

    def set_master_address(self, addr: int) -> None: ...
    def set_outstation_address(self, addr: int) -> None: ...
    def set_server_port(self, port: int) -> None: ...

    def start(self) -> bool: ...
    def stop(self) -> bool: ...
    def isRunning(self) -> bool: ...

    def read_class(self, cls: int = 0) -> bool: ...           # 完整性/事件轮询
    def read_point(self, index: int, group: int, variation: int) -> Any: ...
    def write_point(self, index: int, value, group: int, variation: int) -> bool: ...
    def operate(self, index: int, value, sbo: bool = True, frame_type: int = 2) -> bool: ...
    def sync_time(self) -> bool: ...
    def enable_unsolicited(self, enabled: bool) -> bool: ...
    def set_on_data_callback(self, callback) -> None: ...
```

### 4.4 Handler 层（接口对齐）

`src/device/protocol/dnp3_handler.py`，实现 `DNP3ServerHandler(ServerHandler)` 与 `DNP3ClientHandler(ClientHandler)`，接口与 `iec104_handler.py` / `modbus_handler.py` 完全一致：

- `initialize(config)`：解析 `config["runtime"]`（DNP3 参数）、`config["ip"/"port"]`、地址配置；
- `start() / stop()`：启动/停止 Dnp3Server / Dnp3Client；
- `read_value(point)` / `write_value(point, value)`：按测点索引读写（同步）；`read_value_async / write_value_async` 提供异步包装；
- `add_points(points)`：将测点注册到 Outstation（按类型调用 `add_binary_input` / `add_analog_input` / `add_binary_output` / `add_analog_output`）；
- 遥控/遥调：服务端通过 `set_on_command_callback` 接收 Master 控制；客户端 `operate()` 下发；
- `get_captured_messages / clear_captured_messages`：报文捕获（`MessageCapture` + `add_tx/add_rx`）。

**Device 集成**（`src/device/core/device.py`）：

```python
handler_map = {
    ...
    ProtocolType.Dnp3Server: lambda: DNP3ServerHandler(self.log),
    ProtocolType.Dnp3Client: lambda: DNP3ClientHandler(self.log),
}
```

并在 `Device` 增加 `initDnp3Server() / initDnp3Client()` 方法（与 `initIec104Server` 等一致）。

### 4.5 测点模型与四遥映射

沿用现有 `Yc / Yx / Yk / Yt` 测点类与数据库结构，扩展 DNP3 特有字段（存于既有扩展字段或新增列）：

| 测点类型 | DNP3 对象 | 默认变体 | 关键字段 |
| --- | --- | --- | --- |
| YC 遥测 | G30 Analog Input | G30V5（32bit+品质） | index、死区（deadband）、事件类 |
| YX 遥信 | G1 Binary Input | G1V1（单比特） | index、事件类 |
| YK 遥控 | G10 Binary Output | G10V2（控制码） | index、command_type（Trip/Close/Latch/Pulse） |
| YT 遥调 | G40 Analog Output | G40V1（32bit） | index、SBO/DO 选择 |

- **寻址**：DNP3 使用 **Index** 寻址（区别于 Modbus 地址），复用测点 `reg_addr` 字段承载 index；
- **事件**：YC/YX 可配置事件类（Class 1/2/3）与死区，值变化超过死区产生事件（G2/G32），供 Master 事件轮询或未请求上送；
- 品质位映射：DNP3 品质（Online/Restart/Comm_Lost/Remote/Overflow/...）→ 现有 `quality_descriptor` 字段，沿用 IV/NT/SB/BL/OV 的展示体系。

### 4.6 报文解析器

新增 `src/device/core/message/parsers/dnp3.py`，实现 `parse_dnp3_frame(data: bytes) -> list[dict]`，输出与现有 `modbus.py` / `iec104.py` 解析器一致的结构（时间、方向、原始 HEX、逐字段解析）：

- 链路层：起始字、长度、控制字（DIR/PRM/FCB/FCV/功能码）、目的/源地址、CRC 校验；
- 传输层：FIR/FIN、序号、分片重组；
- 应用层：应用控制字（FIR/FIN/CON/UNS/SEQ）、功能码（请求/响应）、IIN（G80）、对象头（组/变体/限定词/数量）、对象数据（按变体解码为值+品质）；
- 类型/原因映射：功能码与对象组映射为中文描述（如"读 Class 0 完整性轮询"、"SBO 选择"）。

### 4.7 协议运行参数（runtime_config）

`src/device/protocol/runtime_config.py` 增加 DNP3 字段（`PROTOCOL_FIELDS`），供前端表单与后端归一化共用：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| local_address | 1 | 本端 DNP3 地址（服务端/客户端） |
| remote_address | 1 | 对端 DNP3 地址 |
| address_size | 1 | 地址长度（1/2 字节） |
| link_confirm | 开 | 链路层确认 |
| app_confirm | 开 | 应用层确认 |
| unsolicited_enabled | 关 | 未请求响应（服务端） |
| integrity_interval | 60s | 完整性轮询周期（客户端） |
| event_poll_interval | 10s | 事件轮询周期（客户端） |
| time_sync_enabled | 开 | 时间同步（客户端） |
| event_buffer_size | 1000 | 事件缓冲（服务端） |
| connection_timeout / command_timeout | 3000ms | 超时 |
| max_connections | 0 | 最大并发连接（服务端，0 不限制） |

### 4.8 数据库与通道 API

- 通道 `protocol_type` 数值 5；`PROTOCOL_DEFAULT_PORTS` 增加 `[5]: 20000`；
- 通道创建/更新、设备构建走现有通用流程（`ChannelService` / `GeneralDeviceBuilder`），无需新增表；
- 测点表沿用现有列，index 存入 `reg_addr`；新增字段（deadband、event_class、sbo 模式）先放入 `point` 扩展 JSON 或新增可空列（按 `plan/architecture/database-v4-point-table-reuse-design.md` 的扩展策略评估）。

## 5. 前端设计

### 5.1 协议常量

`front/src/constants/protocol.ts`：

```ts
export const PROTOCOL_TYPE = { ..., DNP3: 5 } as const;
PROTOCOL_DEFAULT_PORTS[5] = 20000;
PROTOCOL_DEFAULT_CLIENT_IP[5] = "127.0.0.1";
```

### 5.2 设备表单与协议参数

- `DeviceFormConfig.vue`：协议下拉增加 **DNP3**（服务端/客户端两种连接模式，客户端走 TCP）；
- `DeviceProtocolParams.vue`：新增 DNP3 参数分组（地址、链路/应用确认、未请求、轮询间隔、事件缓冲、超时等，字段与 4.7 对应）；
- TLS：第一版可选（pydnp3 支持 TLS，参照 `iec104/tls.py` 的证书模型接入 `security` 配置，作为二期）。

### 5.3 测点配置

- `AddPointDialog.vue`：DNP3 设备显示"索引（Index）"字段（复用地址输入框文案调整）、可选对象组/变体下拉、死区、事件类；
- 测点表格帧类型/颜色、批量读取（按类读取）、自动读取沿用现有逻辑。

### 5.4 报文查看

- `MessageViewPanel` / 解析器接入 `parsers/dnp3.py`；
- 前端 `messageView` 区域增加 DNP3 报文说明（链路/传输/应用三层）。

### 5.5 i18n

`zh-CN.ts` / `en-US.ts` 增加：协议名（DNP3）、连接模式、地址/确认/未请求/轮询/死区/事件类等字段文案、报文解析描述。

## 6. 实施计划

| 阶段 | 内容 | 交付 |
| --- | --- | --- |
| P0 | pydnp3 依赖引入（含 Windows/Linux wheel 构建），`ProtocolType`/前端常量/端口接入 | 空通道可创建/启动 |
| P1 | `src/proto/dnp3`：Outstation 封装 + 测点注册（G1/G30/G10/G40），服务端 Handler，Device 集成 | 服务端可被第三方 Master 轮询 |
| P2 | Master 封装 + 客户端 Handler：完整性轮询、读、时间同步、SBO/DO 控制 | 客户端可读真实 Outstation |
| P3 | 报文解析器（三层解析）+ 报文查看 + i18n | 报文查看可用 |
| P4 | 前端：协议参数表单、测点配置（index/死区/事件类）、模拟配置联动 | 全流程可用 |
| P5 | 事件/未请求、品质映射、测试完善、互操作验证 | 发布 |

## 7. 测试计划

- 单元：`apply` 参数归一化、四遥映射、地址 1/2 字节、事件死区；
- 集成：本系统 Master ↔ 本系统 Outstation（自测环）；第三方实现互操作（如 opendnp3 工具、真实 RTU）；
- 自动化：`tests/services/`、`tests/web/api/` 覆盖通道 CRUD、测点注册、读写与控制；
- 验证项：完整性轮询返回全部测点、事件轮询/未请求、SBO 两段式控制、时间同步、断线重连、报文解析三层字段、多设备并发。

## 8. 风险与说明

- **pydnp3 依赖体积与构建**：opendnp3 为 C++ 库，Windows wheel 需在 CI 预构建（参照 c104 处理）；
- **变体覆盖范围**：第一版限定常用变体（G1V1/V2、G30V1/V2/V5/V6、G10V2、G40V1/V2、G50V1、G60V1-V4），后续按需扩展；
- **未请求响应**：opendnp3 未请求行为与部分国产设备实现有差异，互操作测试重点覆盖；
- **地址与链路参数**：1/2 字节地址、链路确认策略需两端一致，界面参数化并给出默认值；
- **串口链路**：第一版仅 TCP，串口（RS-232/485）与 TLS 作为二期；
- **回退**：新增协议类型与字段不影响既有协议；DNP3 通道删除时沿用现有清理逻辑。

## 9. 参考

- IEEE 1815-2012 DNP3 标准
- opendnp3 / pydnp3：https://github.com/automatak/opendnp3
- DNP3 协议介绍：https://www.dnp.org/
