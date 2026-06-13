# IEC 61850 Reports 报告功能实现计划

> 版本：1.0
> 日期：2026-05-30
> 状态：规划中


## 1. 概述

IEC 61850 报告（Reporting）是变电站自动化系统中**数据主动推送**的核心机制。与 MMS 轮询不同，报告机制允许服务器在数据变化或事件发生时主动将数据发送给订阅的客户端，显著降低网络带宽占用和响应延迟。

IEC 61850 标准定义了两种报告控制块（RCB）：

| 类型 | 名称 | 说明 |
|------|------|------|
| **BRCB** | Buffered Report Control Block | 缓冲报告控制块，通信中断时缓存报告事件，恢复后补发 |
| **URCB** | Unbuffered Report Control Block | 非缓冲报告控制块，通信中断时丢失事件，不缓存 |

### 当前状态

**已完成的部分：**

- ✅ `ReportsPlugin` 骨架代码（`plugins/reports/__init__.py`）—— 已注册到插件系统，可通过 `client.reports` 访问
- ✅ `RCBInfo` 数据类（`defs/types.py`）—— `name`、`ref`、`rcb_type` 字段
- ✅ `AcsiClass.BRCB / URCB` 常量（`defs/constants.py`）
- ✅ `FunctionalConstraint.RP = "RP"` 未缓冲报告 FC 常量
- ✅ ModelExporter ICD XML 中的 `<ReportControl>` 节点生成
- ✅ C++ 层（`61850cpp/`）完整的报告订阅/回调/数据处理
- ✅ 前端 `Reports` 分类已定义（`protocol.ts`、`channelApi.ts`）

**待实现的部分：**

- ❌ `ReportsPlugin.discover_rcbs()` —— 发现 RCB
- ❌ `ReportsPlugin.enable_report()` —— 使能报告
- ❌ `ReportsPlugin.disable_report()` —— 禁用报告
- ❌ 报告数据接收回调机制
- ❌ 服务端报告控制块注册
- ❌ 后端 Web API（报告管理端点）
- ❌ 前端 Reports 管理 UI 组件
- ❌ 前端 i18n 国际化


## 2. 总体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend (Vue 3)                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  IEC61850 侧边栏树                                          │    │
│  │  └── Device                                                  │    │
│  │      ├── GOOSE         → 跳转 goose 页面                       │    │
│  │      ├── Reports       → 跳转报告管理页面 [新增]              │    │
│  │      ├── DataSets      → 展开树形结构                          │    │
│  │      └── Data Model    → 展开树形结构                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ReportsManager.vue [新增]                                    │    │
│  │  -------------------------------------------------------      │    │
│  │  左侧树: LD → LN → RCB 列表                                 │    │
│  │  右侧详情:                                                    │    │
│  │  ┌──────────────────────────────────────────────────────┐   │    │
│  │  │  RCB 属性: 名称 / 类型 / rptID / DataSet / bufTime / ...│   │    │
│  │  │  TrgOps: ☑ dchg  ☐ qchg  ☐ dupd  ☐ period  ☐ gi    │   │    │
│  │  │  OptFields: ☐ seqNum  ☐ timeStamp  ☐ dataSet  ...   │   │    │
│  │  │  [使能] [禁用] [立即触发GI]                            │   │    │
│  │  └──────────────────────────────────────────────────────┘   │    │
│  │  如已使能，显示最近接收的报告数据表格                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  i18n: zh-CN / en-US Reports 相关翻译 [新增]                │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP JSON
┌──────────────────────────▼──────────────────────────────────────────┐
│                     Backend (FastAPI)                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  src/web/api/channel/report.py [新增]                        │    │
│  │  - GET    /reports/{channel_id}       列出 RCB               │    │
│  │  - POST   /reports/{channel_id}/enable   使能报告            │    │
│  │  - POST   /reports/{channel_id}/disable  禁用报告            │    │
│  │  - POST   /reports/{channel_id}/gi       触发GI              │    │
│  │  - GET    /reports/{channel_id}/data    获取报告数据         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  src/web/api/schemas/report.py [新增]                        │    │
│  │  Pydantic 请求/响应模型                                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                 IEC61850 协议层 (src/proto/iec61850/)                │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  plugins/reports/ [待实现]                                   │    │
│  │  ├── __init__.py    ReportsPlugin 主类                       │    │
│  │  ├── brcb.py        BRCB 操作 (使能/禁用/读取)              │    │
│  │  ├── urcb.py        URCB 操作 (使能/禁用/读取)              │    │
│  │  ├── manager.py     ReportManager (多 RCB 管理) [服务端]     │    │
│  │  └── callback.py    报告接收回调处理                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  pyiec61850 (libiec61850 Python SWIG 绑定)                   │    │
│  │  API 依赖:                                                   │    │
│  │  - IedConnection_getLogicalNodeDirectory (AcsiClass.BRCB/URCB)│   │
│  │  - IedConnection_getRCBValues                                │    │
│  │  - IedConnection_setRCBValues                                │    │
│  │  - IedConnection_installReportHandler                        │    │
│  │  - IedConnection_uninstallReportHandler                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
客户端请求使能报告                  服务器推送报告数据
       │                                    │
       ▼                                    ▼
┌──────────────┐                    ┌──────────────┐
│  enable_report│                    │  回调函数     │
│  (rcb_ref)    │                    │ onReport()   │
└──────┬───────┘                    └──────┬───────┘
       │                                    │
       ▼                                    ▼
┌──────────────┐                    ┌──────────────┐
│ 1. getRCBValues 读取当前值       │ 解析 MMS 数据  │
│ 2. 设置 OptFlds / TrgOps          │ 转换为 Python  │
│ 3. 设置 RptEna = True             │ 存入报告缓存   │
│ 4. installReportHandler 注册回调  │ WebSocket 通知 │
│ 5. setRCBValues 写回服务器       │ (可选)         │
└──────────────┘                    └──────────────┘
```


## 3. 详细设计

### 3.1 ReportsPlugin 插件

**文件：** `src/proto/iec61850/plugins/reports/__init__.py`（完整实现）

#### 3.1.1 核心接口

```python
class ReportsPlugin:
    """Reports 插件 - 管理 BRCB/URCB 报告控制块"""

    def __init__(self):
        self._connection = None
        self._registry = None
        self._initialized = False
        self._active_reports: Dict[str, ReportSubscription] = {}  # rcb_ref -> subscription
        self._data_cache: Dict[str, List[Dict]] = {}              # rcb_ref -> 报告数据历史

    @property
    def name(self) -> str: return "reports"

    @property
    def available(self) -> bool: return HAS_IEC61850

    def initialize(self, connection, **kwargs):
        """初始化，接收 connection 和 registry"""
        self._connection = connection
        self._registry = kwargs.get("registry")
        self._initialized = True
        log.info("Reports 插件已初始化")

    def shutdown(self):
        """关闭所有活跃报告，释放资源"""
        for rcb_ref in list(self._active_reports.keys()):
            self.disable_report(rcb_ref)
        self._connection = None
        self._registry = None
        self._initialized = False
```

#### 3.1.2 方法设计

##### `discover_rcbs(ld: str = "", ln: str = "") -> List[Dict]`

**功能：** 发现服务端报告控制块（BRCB 和 URCB）

**实现参考：** ModelExporter 的 `_discover_rcbs()` 方法

**流程：**
1. 获取逻辑设备列表（如未指定 ld）
2. 对每个 LD → LN，调用 `IedConnection_getLogicalNodeDirectory()` 传入 `AcsiClass.BRCB` / `AcsiClass.URCB`
3. 解析返回的 LinkedList，提取 RCB 名称和引用
4. 对每个 RCB，进一步读取其属性值（通过 getRCBValues 或直接读取 DO 属性）

**返回值：**
```python
[
    {
        "name": "brcb01",
        "ref": "LD0/LLN0.brcb01",
        "rcb_type": "BRCB",
        "ld": "LD0",
        "ln": "LLN0",
        "rpt_id": "brcb01",
        "rpt_ena": False,
        "data_set_ref": "LD0/LLN0$dsReport1",
        "conf_rev": 1,
        "buf_time": 0,
        "trg_ops": {"dchg": True, "qchg": False, "dupd": False, "period": False, "gi": True},
        "opt_fields": {"seq_num": True, "time_stamp": True, "data_set": True,
                        "reason_code": True, "data_ref": False, "entry_id": True, "config_ref": False, "buf_ovfl": False},
        "intg_period": 0,     # 仅 URCB
        "purge_buf": False,   # 仅 BRCB
        "entry_id": None,     # 仅 BRCB
        "time_of_entry": None,# 仅 BRCB
    },
    ...
]
```


##### `enable_report(rcb_ref: str, gi: bool = True) -> bool`

**功能：** 使能指定 RCB，订阅报告

**流程：**
1. 校验连接状态和 rcb_ref
2. 调用 `IedConnection_getRCBValues(conn, rcb_ref)` 获取当前 RCB 属性
3. 设置 `RptEna = True`
4. 设置 `TrgOps`（dchg/qchg/dupd/period/gi）
5. 设置 `OptFields`（seqNum/timeStamp/dataSet/reasonCode 等）
6. 调用 `IedConnection_installReportHandler(conn, rcb_ref, callback, user_data)` 注册 C 回调
7. 调用 `IedConnection_setRCBValues(conn, rcb, changes)` 将修改后的 RCB 写回服务器
8. 保存 subscription 状态到 `_active_reports`

**libIEC61850 API 参考（C++ 层 `enableReport()`）：**
```cpp
// 参考 61850cpp/proto_61850_mms_client.cpp enableReport():
// 1. IedConnection_getRCBValues(conn, rcb_ref, &rcb, &error)
// 2. ClientReportControlBlock_setRptEna(rcb, true)
// 3. 设置 OptFlds / TrgOps 等属性
// 4. IedConnection_installReportHandler(conn, rcb_ref, reportCallbackFunction, param)
// 5. IedConnection_setRCBValues(conn, rcb, &changes, &error)
```


##### `disable_report(rcb_ref: str) -> bool`

**功能：** 禁用指定 RCB，取消报告订阅

**流程：**
1. 调用 `IedConnection_uninstallReportHandler(conn, rcb_ref)`
2. 读取 RCB 当前值，设置 `RptEna = False`
3. 调用 `setRCBValues` 写回服务器
4. 从 `_active_reports` 移除
5. 可选：保留 `_data_cache` 中的历史数据供后续查询


##### `trigger_gi(rcb_ref: str) -> bool`

**功能：** 触发一次 GI（General Interrogation，通用查询），立即生成一次完整报告

**流程：**
1. 读取 RCB 当前值
2. 设置 `GI = True`
3. 调用 `setRCBValues` 写回服务器
4. GI 为自复位（self-clearing），服务器收到后立即生成一次包含所有数据值的报告


##### `get_report_data(rcb_ref: str) -> List[Dict]`

**功能：** 获取指定 RCB 最近接收的报告数据

**返回值：**
```python
[
    {
        "entry_id": "0x0001",
        "time_stamp": "2026-05-30T10:00:00.000",
        "reason_code": "data-change",
        "data_set": "LD0/LLN0$dsReport1",
        "values": {
            "LD0/MMXU1.TotW.mag.f": 123.45,
            "LD0/MMXU1.TotV.mag.f": 220.0,
            ...
        },
        "seq_num": 1,
    },
    ...
]
```


##### `list_active_reports() -> List[Dict]`

**功能：** 列出当前活跃（已使能）的报告订阅

**返回值：**
```python
[
    {"rcb_ref": "LD0/LLN0.brcb01", "rcb_type": "BRCB",
     "rpt_ena": True, "enabled_since": "2026-05-30T10:00:00"},
    ...
]
```


### 3.2 BRCB 与 URCB 子模块

#### 3.2.1 BRCB 操作（`brcb.py`）

```python
class BrcbHandler:
    """BRCB (缓冲报告控制块) 操作"""

    @staticmethod
    def get_rcb_values(connection, rcb_ref: str) -> Optional[Dict]:
        """获取 BRCB 所有属性值（含 entryId, timeOfEntry, purgeBuf 等缓冲特有属性）"""
        ...

    @staticmethod
    def set_rpt_ena(connection, rcb_ref: str, enable: bool) -> bool:
        """设置 RptEna（含缓冲模式处理）"""
        ...

    @staticmethod
    def purge_buffer(connection, rcb_ref: str) -> bool:
        """清除 BRCB 缓冲队列"""
        ...
```

#### 3.2.2 URCB 操作（`urcb.py`）

```python
class UrcbHandler:
    """URCB (非缓冲报告控制块) 操作"""

    @staticmethod
    def get_rcb_values(connection, rcb_ref: str) -> Optional[Dict]:
        """获取 URCB 所有属性值（无缓冲相关属性）"""
        ...

    @staticmethod
    def set_rpt_ena(connection, rcb_ref: str, enable: bool) -> bool:
        """设置 RptEna"""
        ...
```

### 3.3 报告回调处理（`callback.py`）

#### 3.3.1 ReportCallbackParameter 结构

```python
@dataclass
class ReportCallbackParameter:
    """报告回调参数"""
    rcb_ref: str
    on_report: Callable[[Dict], None]
```

#### 3.3.2 回调函数

```python
# 静态回调（C 回调需要静态函数）
def _report_callback_wrapper(param_ptr, report):
    """C 回调包装器，将 C 的 ClientReport 转换为 Python 字典"""
    ...

def parse_report_to_dict(report) -> Dict:
    """解析 ClientReport 为可序列化的 Python 字典

    解析内容:
    - report.rptId
    - report.dataSet
    - report.confRev
    - report.entryID (BRCB)
    - report.seqNum
    - report.timeOfEntry
    - report.dataValues (MmsValue 数组)
    - report.reasonCodes (Entry: data-change / quality-change / data-update / integrity)
    """
    ...
```

### 3.4 服务端报告管理（`manager.py`）

**用途：** 在服务端（IEC61850Server）创建和管理报告控制块，使 EMS 仿真的服务端设备具备报告发布能力。

#### 3.4.1 ReportManager

```python
class ReportManager:
    """服务端报告管理器

    在 IedModel 的 LLN0 下创建 ReportControlBlock，
    管理 RCB 生命周期和报告生成。
    """

    def __init__(self, builder, model_name: str = "EMS"):
        self._builder = builder
        self.model_name = model_name
        self._rcb_list: List[Dict] = []
        self._model_changed: bool = False

    def register_rcb(
        self,
        ld_inst: str,
        name: str,
        rcb_type: str = "BRCB",   # "BRCB" 或 "URCB"
        rpt_id: str = "",
        data_set_ref: str = "",
        conf_rev: int = 1,
        buf_time: int = 0,
        intg_period: int = 0,
        trg_ops: Optional[Dict] = None,
        opt_fields: Optional[Dict] = None,
    ) -> bool:
        """在 MMS 模型中注册 ReportControlBlock

        使用 libIEC61850 API:
        - ReportControlBlock_create(name, lln0, rptId, dataSetRef, confRev, buffered, bufTime, intgPeriod)
        或通过 SCL 模型在 ICD 中定义。
        """
        ...

    def browse_rcbs(self) -> List[Dict]:
        """返回服务器上所有已注册的 RCB 目录"""
        ...

    @property
    def rcb_list(self) -> List[Dict]:
        return self._rcb_list
```

**注意事项：** libIEC61850 的服务端 API 中，`ReportControlBlock` 的创建方式取决于 C 库版本。如果 Python SWIG 绑定未暴露 `ReportControlBlock_create`，则采用以下替代方案：

| 方案 | 说明 | 优先级 |
|------|------|--------|
| 直接 API | 使用 `ReportControlBlock_create()` | 优先 |
| SCL ICD 注入 | 先导出 ICD，在 ICD 中声明 `<ReportControl>`，然后重新加载 | 备选 |
| MMS 写操作 | 客户端通过 MMS 写操作动态创建 RCB（取决于设备支持） | 备选 |


### 3.5 后端 Web API

**文件：** `src/web/api/channel/report.py`（新增）
**文件：** `src/web/api/schemas/report.py`（新增）

#### 3.5.1 请求/响应 Schema

```python
# schemas/report.py

class RcbListRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")

class RcbInfoResponse(BaseModel):
    """单个 RCB 信息"""
    name: str
    ref: str
    rcb_type: str       # "BRCB" 或 "URCB"
    ld: str = ""
    ln: str = ""
    rpt_ena: bool = False
    rpt_id: str = ""
    data_set_ref: str = ""
    ...

class RcbListResponse(BaseModel):
    rcbs: List[RcbInfoResponse] = []

class EnableReportRequest(BaseModel):
    channel_id: int
    rcb_ref: str
    gi: bool = True     # 是否同时触发 GI

class GiRequest(BaseModel):
    channel_id: int
    rcb_ref: str

class ReportDataRequest(BaseModel):
    channel_id: int
    rcb_ref: str
    limit: int = 100
```

#### 3.5.2 路由设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/channels/iec61850/reports/list` | 列出所有 RCB（客户端发现） |
| POST | `/api/channels/iec61850/reports/enable` | 使能报告 |
| POST | `/api/channels/iec61850/reports/disable` | 禁用报告 |
| POST | `/api/channels/iec61850/reports/gi` | 触发 GI |
| POST | `/api/channels/iec61850/reports/data` | 获取报告数据 |

#### 3.5.3 IEC61850 结构 API 集成

**修改 `iec61850.py` 的 `get_iec61850_structure` 端点：**

```python
# 在获取 structure 时，从 ReportsPlugin 获取发现的 RCB
if hasattr(protocol_handler, 'reports') and protocol_handler.reports:
    rcbs = protocol_handler.reports.discover_rcbs()
    report_items = [f"{rcb['ref']} ({rcb['rcb_type']})" for rcb in rcbs]
else:
    report_items = []

structure = {
    "GOOSE": goose_items,
    "Reports": report_items,     # ← 填充真实数据
    ...
}
```

#### 3.5.4 路由注册

**修改 `src/web/api/channel/__init__.py`：** 注册 `report_router`

**若依赖 WebSocket 实时推送：**

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| **轮询** | 前端定时调用 GET `/data` 获取最新报告数据 | MVP 快速实现 |
| **WebSocket** | 后端收到报告回调后主动推送到前端 | 最终方案 |

**推荐阶段：** MVP 阶段使用轮询（前端每 1-2 秒拉取），后续升级为 WebSocket。


### 3.6 前端 UI

#### 3.6.1 ReportsManager 组件

**文件：** `front/src/components/reports/ReportsManager.vue`（新增）

**布局：**

```
┌──────────────────────────────────────────────────────┐
│  Reports Management                                  │
│  ──────────────────────────────────────────────────   │
│  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  [刷新]       │  │  RCB 详情                    │  │
│  │               │  │  ───────────────────────      │  │
│  │  ▼ LD0        │  │  名称: brcb01                │  │
│  │    └▼ LLN0    │  │  类型: BRCB (缓冲)           │  │
│  │      ├ brcb01 │  │  rptID: brcb01               │  │
│  │      └ brcb02 │  │  DataSet: dsReport1          │  │
│  │               │  │  confRev: 1                  │  │
│  │  ▼ LD1        │  │  RptEna: 🟢 已使能           │  │
│  │    └ ▼ GGIO1  │  │                              │  │
│  │      └ urcb01 │  │  TrgOps:                     │  │
│  │               │  │  ☑ dchg ☐ qchg              │  │
│  │               │  │  ☐ dupd ☑ period             │  │
│  │               │  │  ☑ gi                        │  │
│  │               │  │                              │  │
│  │               │  │  [使能] [禁用] [触发GI]      │  │
│  │               │  ├──────────────────────────────┤  │
│  │               │  │  最近报告数据(5条)            │  │
│  │               │  │  ┌────┬──────┬──────────┐   │  │
│  │               │  │  │#   │ 时间  │ 变化原因  │   │  │
│  │               │  │  ├────┼──────┼──────────┤   │  │
│  │               │  │  │ 1  │10:00 │dchg      │   │  │
│  │               │  │  │ 2  │09:59 │period    │   │  │
│  │               │  │  └────┴──────┴──────────┘   │  │
│  └──────────────┘  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**左侧树结构：** 从后端 `/iec61850-structure` 获取 Reports 分类数据
**右侧详情：** 选择 RCB 后显示详细属性、操作按钮、报告数据

#### 3.6.2 侧边栏集成

**修改 `front/src/composables/useIec61850Tree.ts`：**

- Reports 分类条目携带 `linkTo: '/reports'` 属性
- 点击 Reports 树节点时通过 `router.push('/reports')` 导航到 Reports 管理页面

**修改 `front/src/router/index.ts`：** 新增 `/reports` 路由

**修改 `front/src/views/SideBar.vue`：** 处理 Reports 节点 `linkTo` 导航

#### 3.6.3 导航入口

| 入口 | 位置 | 说明 |
|------|------|------|
| 侧边栏 | IEC61850 设备 → Reports 节点 | 设备级 Reports 入口 |
| URL | `/reports` | 直接访问（全局 Reports 管理） |

#### 3.6.4 API 封装

**文件：** `front/src/api/reportApi.ts`（新增）

```typescript
export interface RcbInfo {
  name: string;
  ref: string;
  rcb_type: string;
  ld: string;
  ln: string;
  rpt_ena: boolean;
  rpt_id: string;
  data_set_ref: string;
  conf_rev: number;
  buf_time: number;
  trg_ops: TrgOps;
  opt_fields: OptFields;
}

export interface ReportDataEntry {
  seq_num: number;
  time_stamp: string;
  reason_code: string;
  data_set: string;
  values: Record<string, any>;
}

// API 函数
export async function listRcbs(channelId: number): Promise<RcbInfo[]>
export async function enableReport(channelId: number, rcbRef: string, gi?: boolean): Promise<boolean>
export async function disableReport(channelId: number, rcbRef: string): Promise<boolean>
export async function triggerGi(channelId: number, rcbRef: string): Promise<boolean>
export async function getReportData(channelId: number, rcbRef: string, limit?: number): Promise<ReportDataEntry[]>
```


### 3.7 数据模型扩展

#### 3.7.1 `defs/types.py` — 扩展 RCBInfo

```python
@dataclass
class RCBInfo:
    """报告控制块 (RCB) 信息"""
    name: str = ""
    ref: str = ""
    rcb_type: str = ""          # "BRCB" 或 "URCB"
    ld: str = ""
    ln: str = ""
    rpt_id: str = ""
    rpt_ena: bool = False
    data_set_ref: str = ""
    conf_rev: int = 1
    buf_time: int = 0           # 缓冲时间 (ms)
    intg_period: int = 0        # 完整性周期 (ms)，仅 URCB
    purge_buf: bool = False     # 清除缓冲，仅 BRCB
    entry_id: Optional[bytes] = None  # 入口 ID，仅 BRCB
    time_of_entry: Optional[int] = None  # 入口时间，仅 BRCB
    trg_ops: "TrgOps" = field(default_factory=lambda: TrgOps())
    opt_fields: "OptFields" = field(default_factory=lambda: OptFields())


@dataclass
class TrgOps:
    """触发选项 (Trigger Options)"""
    dchg: bool = True       # 数据变化触发
    qchg: bool = False      # 品质变化触发
    dupd: bool = False      # 数据更新触发
    period: bool = False    # 周期触发
    gi: bool = True         # 通用查询触发


@dataclass
class OptFields:
    """可选字段 (Optional Fields)"""
    seq_num: bool = True
    time_stamp: bool = True
    data_set: bool = True
    reason_code: bool = True
    data_ref: bool = False
    entry_id: bool = True
    config_ref: bool = False
    buf_ovfl: bool = False


@dataclass
class ReportDataEntry:
    """单条报告数据条目"""
    seq_num: int = 0
    time_stamp: str = ""
    reason_codes: Dict[str, str] = field(default_factory=dict)
    data_values: Dict[str, Any] = field(default_factory=dict)
    entry_id: Optional[bytes] = None
    conf_rev: int = 1
```


### 3.8 国际化支持

#### zh-CN 新增

```typescript
report: {
  title: '报告管理',
  discover: '发现 RCB',
  enable: '使能',
  disable: '禁用',
  gi: '触发 GI',
  brcb: '缓冲报告 (BRCB)',
  urcb: '非缓冲报告 (URCB)',
  rptEna: '报告状态',
  enabled: '已使能',
  disabled: '已禁用',
  rptId: '报告标识',
  dataSet: '数据集',
  confRev: '配置版本',
  bufTime: '缓冲时间 (ms)',
  intgPeriod: '完整性周期 (ms)',
  trgOps: '触发选项',
  dchg: '数据变化',
  qchg: '品质变化',
  dupd: '数据更新',
  period: '周期',
  giLabel: '通用查询',
  optFields: '可选字段',
  seqNum: '序号',
  timeStamp: '时标',
  dataSetField: '数据集引用',
  reasonCode: '变化原因',
  dataRef: '数据引用',
  entryId: '入口 ID',
  configRef: '配置引用',
  bufOvfl: '缓冲溢出',
  reportData: '报告数据',
  seqNumShort: '#',
  reason: '原因',
  time: '时间',
  values: '数值',
  noData: '暂无报告数据',
  enableSuccess: '报告使能成功',
  disableSuccess: '报告禁用成功',
  giSuccess: 'GI 触发成功',
  enableFailed: '报告使能失败',
  disableFailed: '报告禁用失败',
  giFailed: 'GI 触发失败',
}
```


## 4. 分阶段实施计划

### Phase 1: 后端插件基础实现（Priority: P0 | 预估: 3 天）

| 任务 | 说明 | 产出 |
|------|------|------|
| **1.1 扩展 RCBInfo 数据类** | 在 `defs/types.py` 中补充 TrgOps、OptFields、ReportDataEntry，扩展 RCBInfo 字段 | `defs/types.py` |
| **1.2 实现 BRCB/URCB 操作** | 创建 `brcb.py` / `urcb.py`，封装 getRCBValues, setRCBValues, setRptEna | `plugins/reports/brcb.py`、`urcb.py` |
| **1.3 实现 report 回调** | 创建 `callback.py`，封装 C 回调注册/注销，MmsValue 数组解析 | `plugins/reports/callback.py` |
| **1.4 完整实现 ReportsPlugin** | 填充 `discover_rcbs()`、`enable_report()`、`disable_report()`、`trigger_gi()`、`get_report_data()` | `plugins/reports/__init__.py` |
| **1.5 ReportsPlugin 单元测试** | mock pyiec61850 测试发现/使能/禁用流程 | `tests/` |

**验收标准：**
- [ ] `ReportsPlugin.discover_rcbs()` 能正确发现实际 IED 的 BRCB 和 URCB
- [ ] `ReportsPlugin.enable_report()` 能成功使能报告，注册回调
- [ ] `ReportsPlugin.disable_report()` 能成功禁用报告，注销回调
- [ ] C 回调能正确解析报告数据并存入缓存
- [ ] 回调线程安全，无内存泄漏

### Phase 2: 服务端报告支持（Priority: P1 | 预估: 2 天）

| 任务 | 说明 | 产出 |
|------|------|------|
| **2.1 实现 ReportManager** | 在服务端 LLN0 下注册 RCB，生成报告控制块 | `plugins/reports/manager.py` |
| **2.2 集成到 IEC61850Server** | 服务端启动时注册默认 RCB（绑定 DataSet），支持报告发布 | `iec61850_server.py` 修改 |
| **2.3 报告生成机制** | 服务端测点值变化时自动生成报告（基于 DataSet 成员的 TrgOps） | `plugins/reports/manager.py` |
| **2.4 报告配置持久化** | 将 RCB 配置保存到 `config.ini` 或数据库，支持启动时自动恢复 | `config.ini` / 数据库 |

**验收标准：**
- [ ] 服务器启动后，客户端 `discover_rcbs()` 能发现服务端注册的 RCB
- [ ] 客户端使能报告后，服务端测点值变化能触发报告推送
- [ ] 异常断开后，BRCB 能缓存事件并在重连后补发

### Phase 3: 后端 Web API（Priority: P0 | 预估: 1 天）

| 任务 | 说明 | 产出 |
|------|------|------|
| **3.1 创建 Pydantic Schema** | 定义 RCB 列表、使能请求/响应等模型 | `schemas/report.py` |
| **3.2 实现 Web API 路由** | 5 个 RESTful 端点（list/enable/disable/gi/data） | `channel/report.py` |
| **3.3 集成到 IEC61850 Structure** | `iec61850-structure` 端点填充 Reports 分类 | `channel/iec61850.py` |
| **3.4 注册路由** | 在 `channel/__init__.py` 注册 report_router | `channel/__init__.py` |

**验收标准：**
- [ ] `POST /iec61850/reports/list` 返回正确的 RCB 列表
- [ ] `POST /iec61850/reports/enable` 成功使能并返回状态
- [ ] `POST /iec61850/reports/disable` 成功禁用
- [ ] `POST /iec61850/reports/gi` 触发 GI
- [ ] `POST /iec61850/reports/data` 返回缓存报告数据
- [ ] `iec61850-structure` 端点的 Reports 字段有真实数据

### Phase 4: 前端 UI（Priority: P0 | 预估: 2 天）

| 任务 | 说明 | 产出 |
|------|------|------|
| **4.1 创建 reportApi.ts** | TypeScript API 封装，类型定义 | `front/src/api/reportApi.ts` |
| **4.2 创建 ReportsManager.vue** | 左侧树 + 右侧详情 + 操作按钮 + 报告数据表格 | `front/src/components/reports/ReportsManager.vue` |
| **4.3 创建 ReportsView.vue** | 报告管理页面 | `front/src/views/ReportsView.vue` |
| **4.4 注册路由** | 添加 `/reports` 路由 | `front/src/router/index.ts` |
| **4.5 侧边栏集成** | Reports 节点 `linkTo` 导航 | `useIec61850Tree.ts`、`SideBar.vue` |
| **4.6 顶部导航栏** | 添加报告管理导航入口 | `AppHeader.vue` |
| **4.7 i18n 翻译** | 中英文报告相关翻译 | `zh-CN.ts`、`en-US.ts` |
| **4.8 API 常量** | 新增 report API 路径常量 | `front/src/constants/api.ts` |

**验收标准：**
- [ ] 左侧树正确显示 LD → LN → RCB 层级
- [ ] 选中 RCB 后右侧显示完整属性
- [ ] 使能/禁用/GI 按钮功能正常
- [ ] 报告数据表格能显示接收到的报告
- [ ] 侧边栏 Reports 节点可点击导航
- [ ] 中英文界面正常切换

### Phase 5: 增强与优化（Priority: P2 | 预估: 2 天）

| 任务 | 说明 | 产出 |
|------|------|------|
| **5.1 WebSocket 实时推送** | 报告回调通过 WebSocket 推送至前端，替代轮询 | `websocket` 集成 |
| **5.2 报告数据持久化** | 将报告数据存入数据库，支持历史查询 | 数据库表 |
| **5.3 报告过滤与搜索** | 按时间/类型/数据引用过滤报告 | UI 增强 |
| **5.4 导出报告数据** | 支持导出报告数据为 CSV/JSON | API + UI |
| **5.5 ICD 导入自动创建 RCB** | 从 ICD/SCD 文件导入时自动创建 RCB 配置 | `ICD importer` |
| **5.6 性能优化** | 高频率报告场景下的内存管理和回调优化 | 性能测试 |


## 5. libIEC61850 API 参考

### 5.1 客户端 API

| API | 说明 | 参数 | 返回值 |
|-----|------|------|--------|
| `IedConnection_getLogicalNodeDirectory(conn, lnRef, acsiClass)` | 获取 LN 下的 RCB 名称列表 | acsiClass: 5=BRCB, 6=URCB | LinkedList |
| `IedConnection_getRCBValues(conn, rcbRef, rcb, error)` | 获取 RCB 所有属性 | rcb: ClientReportControlBlock | IedClientError |
| `IedConnection_setRCBValues(conn, rcb, changes, error)` | 设置 RCB 属性 | changes: 位掩码标识需要修改的属性 | IedClientError |
| `IedConnection_installReportHandler(conn, rcbRef, callback, param)` | 注册报告接收回调 | callback: ReportHandlerFunction | void |
| `IedConnection_uninstallReportHandler(conn, rcbRef)` | 注销报告接收回调 | | void |
| `ClientReportControlBlock_create()` | 创建 ClientRCB 对象 | | ClientReportControlBlock |
| `ClientReportControlBlock_destroy(rcb)` | 销毁 ClientRCB 对象 | | void |
| `ClientReportControlBlock_setRptEna(rcb, value)` | 设置 RptEna | | void |
| `ClientReportControlBlock_setOptFlds(rcb, fields)` | 设置 OptFields | | void |
| `ClientReportControlBlock_setTrgOps(rcb, ops)` | 设置 TrgOps | | void |
| `ClientReportControlBlock_setGI(rcb, value)` | 设置 GI | | void |
| `ClientReportControlBlock_setDataSetRef(rcb, ref)` | 设置 DataSetRef | | void |
| `ClientReportControlBlock_setIntgPd(rcb, period)` | 设置完整性周期 (URCB) | period: ms | void |

### 5.2 报告回调解析 API

| API | 说明 |
|-----|------|
| `ClientReport_getRptId(report)` | 获取报告 ID |
| `ClientReport_getDataSet(report)` | 获取数据集引用 |
| `ClientReport_getConfRev(report)` | 获取配置修订号 |
| `ClientReport_getEntryID(report)` | 获取入口 ID (BRCB) |
| `ClientReport_getSeqNum(report)` | 获取序号 |
| `ClientReport_getTimeOfEntry(report)` | 获取入口时间 (BRCB) |
| `ClientReport_getValues(report)` | 获取数据值数组 (MmsValue) |
| `ClientReport_getReasonCodes(report)` | 获取变化原因编码 |

### 5.3 服务端 API（供参考）

| API | 说明 |
|-----|------|
| `ReportControlBlock_create(name, lln0, rptId, dataSetRef, confRev, buffered, bufTime, intgPeriod)` | 创建报告控制块 |
| `IedServer_setReportControlBlockBufferSize(server, size)` | 设置报告缓冲区大小 |
| `IedServerConfig_setReportBufferSize(config, size)` | 配置报告缓冲区 |

### 5.4 Changes 位掩码常量

```c
RCB_RPT_ENA    = 0x0001
RCB_DAT_SET_REF = 0x0002
RCB_RPT_ID     = 0x0004
RCB_ENA        = 0x0008  // Reserved
RCB_RESERVED   = 0x0010
RCB_CONF_REV   = 0x0020
RCB_TRG_OPS    = 0x0040
RCB_OPT_FLDS   = 0x0080
RCB_BUF_TIME   = 0x0100
RCB_ENTRY_ID   = 0x0200  // BRCB only
RCB_TIME_OF_ENTRY = 0x0400  // BRCB only
RCB_GI         = 0x0800
RCB_INTG_PD    = 0x1000  // URCB only
RCB_PURGE_BUF  = 0x2000  // BRCB only
```


## 6. 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| pyiec61850 未安装 | `available` 返回 False，API 返回 501 Not Implemented |
| 连接断开 | 返回 503 Service Unavailable，前端显示断开提示 |
| setRCBValues 失败 | 记录详细错误日志，返回 enable=False 及错误码 |
| 回调注册失败 | 清理已设置的 RptEna，回滚到初始状态 |
| RCB 引用不存在 | 返回 404，提示用户重新发现 RCB |
| 报告数据缓存溢出 | 按 FIFO 策略淘汰，保留最近 1000 条 |
| 高频率报告 | 缓存去重（同 seqNum 不重复存储），回调中异步处理 |
| C 回调异常 | try/except 捕获异常，记录日志，防止回调链中断 |


## 7. 文件清单

### 后端 — 新增文件

| 文件 | 说明 |
|------|------|
| `src/proto/iec61850/plugins/reports/brcb.py` | BRCB 操作封装 |
| `src/proto/iec61850/plugins/reports/urcb.py` | URCB 操作封装 |
| `src/proto/iec61850/plugins/reports/callback.py` | 报告回调处理 |
| `src/proto/iec61850/plugins/reports/manager.py` | 服务端报告管理器 |
| `src/web/api/schemas/report.py` | Pydantic 数据模型 |
| `src/web/api/channel/report.py` | Web API 路由 |

### 后端 — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/proto/iec61850/plugins/reports/__init__.py` | 完整实现 ReportsPlugin |
| `src/proto/iec61850/defs/types.py` | 扩展 RCBInfo，新增 TrgOps、OptFields、ReportDataEntry |
| `src/web/api/channel/__init__.py` | 注册 report_router |
| `src/web/api/channel/iec61850.py` | `iec61850-structure` 端点填充 Reports 分类 |

### 前端 — 新增文件

| 文件 | 说明 |
|------|------|
| `front/src/api/reportApi.ts` | Reports API 调用层 |
| `front/src/components/reports/ReportsManager.vue` | Reports 管理主组件 |
| `front/src/views/ReportsView.vue` | Reports 页面视图 |

### 前端 — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `front/src/constants/api.ts` | 新增 Reports API 路径常量 |
| `front/src/constants/protocol.ts` | 新增 Reports 状态/颜色常量 |
| `front/src/router/index.ts` | 新增 `/reports` 路由 |
| `front/src/composables/useIec61850Tree.ts` | Reports 分类支持 `linkTo` 导航 |
| `front/src/views/SideBar.vue` | 处理 Reports 节点 `linkTo` 导航 |
| `front/src/components/header/AppHeader.vue` | 新增 Reports 导航入口（可选） |
| `front/src/i18n/locales/zh-CN.ts` | 报告相关中文翻译 |
| `front/src/i18n/locales/en-US.ts` | 报告相关英文翻译 |


## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **libIEC61850 版本差异** | 中 | 高 | 保留多版本兼容逻辑（try_methods 模式），参考 DataSets 插件的处理方式 |
| **`ReportControlBlock_create` 未暴露到 Python SWIG** | 中 | 高 | 备选方案：通过 ICD 声明 RCB，或使用 MMS 写操作创建 |
| **C 回调不能直接调用 Python** | 低 | 高 | 使用 ctypes CFUNCTYPE 包装或静态函数 + 全局字典映射 |
| **报告数据量大时内存溢出** | 低 | 中 | 限制缓存上限（1000 条），FIFO 淘汰策略 |
| **回调线程与主线程冲突** | 中 | 中 | 回调中使用 queue.Queue 异步处理，避免阻塞 C 回调 |


## 9. 验收标准

### Phase 1 验收
- [ ] `ReportsPlugin.discover_rcbs()` 能正确发现实际 IED 的 BRCB 和 URCB
- [ ] `ReportsPlugin.enable_report()` 能成功使能报告
- [ ] `ReportsPlugin.disable_report()` 能成功禁用报告
- [ ] 回调函数能正确接收并解析报告数据

### Phase 2 验收
- [ ] 服务端能发布报告（客户端能订阅并收到报告数据）
- [ ] BRCB 在断开重连后能补发缓存事件

### Phase 3 验收
- [ ] 5 个 Web API 端点全部可用
- [ ] `iec61850-structure` 的 Reports 分类有正确数据

### Phase 4 验收
- [ ] Reports 管理页面完整可用
- [ ] 使能/禁用/GI 操作可交互
- [ ] 报告数据表格正常显示
- [ ] 侧边栏导航正常
- [ ] 中英文界面正常

### 最终验收
- [ ] 全部 4 个 Phase 验收项通过
- [ ] 无内存泄漏和线程安全问题
- [ ] 前后端通信正常（无 500 错误）
- [ ] 用户手册已更新（可选）


## 10. 参考文档

1. IEC 61850-7-2: ACSI 基本通信结构 - 报告模型 (Reporting Model)
2. IEC 61850-8-1: SCSM - MMS 映射 - 报告服务映射
3. libIEC61850 官方文档: [https://libiec61850.com/libiec61850/documentation/](https://libiec61850.com/libiec61850/documentation/)
4. libIEC61850 API 参考: [https://libiec61850.com/libiec61850/apidoc/](https://libiec61850.com/libiec61850/apidoc/)
5. 项目现有文档: `docs/changelog/iec61850-refactoring-plan.md`（插件架构参考）
6. 项目现有文档: `docs/changelog/goose-support.md`（类似功能的实现参考）
