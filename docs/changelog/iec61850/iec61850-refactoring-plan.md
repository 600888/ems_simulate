# IEC 61850 模块化重构计划

> 版本: 1.0  
> 日期: 2026-05-30  
> 状态: 规划中

---

## 1. 现状分析

### 1.1 当前文件结构

```
src/proto/iec61850/
├── __init__.py              # 仅一行注释
├── iec61850_client.py       # 2307 行 - 巨型单体文件
├── iec61850_server.py       # ~1800 行 - 巨型单体文件
├── iec61850_defs.py         # ~99 行 - 仅 LN class 定义
├── iec61850_model_exporter.py # ~500 行 - 模型导出
├── goose_manager.py         # GOOSE 资源管理器
├── goose_publisher.py       # GOOSE 发布
├── goose_subscriber.py      # GOOSE 订阅
├── goose_capture.py         # GOOSE 抓包
└── log.py                   # 日志配置
```

### 1.2 核心问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **代码严重冗余** | 🔴 高 | `_is_full_ref()`, `_parse_ref()`, FC 常量在 client/server 中重复定义 |
| **职责不清** | 🔴 高 | `iec61850_client.py` 混合了连接管理、读写操作、模型发现、DataSet、GOOSE 发现、MMS 转换等 7+ 种职责 |
| **常量散落** | 🟡 中 | IEC_TYPE_*, _DA_PATTERNS, _EXTRA_DA_INFO 等定义在 client.py，但 server/model_exporter 都需要 |
| **无插件架构** | 🟡 中 | 各功能紧耦合，无法按需加载或独立测试 |
| **文件过长** | 🔴 高 | client.py 2307 行、server.py ~1800 行，维护成本极高 |
| **反向依赖** | 🟡 中 | model_exporter 从 client 导入常量，形成不合理的依赖方向 |
| **鲁棒性不足** | 🟡 中 | 大量 try/except pass，缺乏统一的错误处理和重试机制 |

### 1.3 冗余代码清单

| 冗余项 | 位置 | 说明 |
|--------|------|------|
| `_is_full_ref()` | client.py:38, server.py:37 | 完全相同 |
| `_parse_ref()` | client.py:43, server.py:42 | 完全相同 |
| `FC_MX/FC_ST/FC_CO` 常量 | client.py:28-35, server.py:24-34 | 完全相同 |
| `HAS_IEC61850` 检测 | client.py, server.py, goose_*.py | 每个文件重复 |
| `_extract_ln_class()` / `_split_ln_name()` | client.py:1143, server.py:69 | 逻辑相同，实现略有差异 |
| `_infer_frame_type_from_do()` 逻辑 | client.py | 在 server 的 add_point 中也有类似推断 |
| IEC_TYPE_* 常量 | client.py:70-75 | 应在 defs 中定义 |

---

## 2. 重构目标

1. **模块插件化**: GOOSE/SV/Reports/Log/SettingGroups/DataSets/DataModels/Files 各自独立模块
2. **公共定义统一**: 所有共享常量、工具函数提取到 `defs/` 包
3. **消除冗余**: DRY 原则，相同代码只存在一处
4. **现代设计模式**: 使用 Protocol、dataclass、Strategy、Plugin Registry 等
5. **增强鲁棒性**: 统一错误处理、连接重试、类型安全
6. **可测试性**: 每个模块可独立单元测试

---

## 3. 目标架构

### 3.1 目录结构

```
src/proto/iec61850/
├── __init__.py                    # 顶层导出，版本号
├── defs/                          # 公共定义包
│   ├── __init__.py                # 统一导出
│   ├── constants.py               # FC 常量、IEC 类型枚举、ACSI 类常量
│   ├── ln_classes.py              # LN class 分类表 (原 iec61850_defs.py)
│   ├── da_patterns.py             # DA 路径映射 (_DA_PATTERNS, _EXTRA_DA_INFO, _SKIP_DA_NAMES 等)
│   ├── address.py                 # 地址解析工具 (_is_full_ref, _parse_ref, infer_fc, infer_iec_type)
│   └── types.py                   # 数据类定义 (DAInfo, DOInfo, DataSetInfo, PointRef 等)
│
├── core/                          # 核心连接与读写
│   ├── __init__.py
│   ├── connection.py              # IedConnection 生命周期管理 (连接/断开/重连/心跳)
│   ├── mms_value.py               # MmsValue ↔ Python 类型转换
│   ├── linked_list.py             # LinkedList 解析工具
│   ├── reader.py                  # 数据读取 (单点/批量/自动探测)
│   └── writer.py                  # 数据写入 (单点/批量)
│
├── plugins/                       # 功能模块插件
│   ├── __init__.py                # 插件注册表 (PluginRegistry)
│   ├── base.py                    # 插件基类 (Iec61850Plugin Protocol)
│   ├── goose/                     # GOOSE 模块
│   │   ├── __init__.py
│   │   ├── publisher.py           # GOOSE 发布者
│   │   ├── subscriber.py          # GOOSE 订阅者
│   │   ├── capture.py             # GOOSE 抓包引擎
│   │   └── manager.py             # GOOSE 资源管理器
│   │
│   ├── sv/                        # SV (Sampled Values) 模块
│   │   ├── __init__.py
│   │   ├── publisher.py           # SV 发布者
│   │   ├── subscriber.py          # SV 订阅者
│   │   └── manager.py             # SV 资源管理器
│   │
│   ├── reports/                   # Reports (报告) 模块
│   │   ├── __init__.py
│   │   ├── brcb.py                # 缓冲报告控制块 (BRCB)
│   │   ├── urcb.py                # 非缓冲报告控制块 (URCB)
│   │   └── manager.py             # 报告管理器
│   │
│   ├── log/                       # Log (日志) 模块
│   │   ├── __init__.py
│   │   ├── lcb.py                 # 日志控制块 (LCB)
│   │   └── manager.py             # 日志管理器
│   │
│   ├── setting_groups/            # Setting Groups (定值组) 模块
│   │   ├── __init__.py
│   │   ├── sgcb.py                # 定值组控制块 (SGCB)
│   │   └── manager.py             # 定值组管理器
│   │
│   ├── datasets/                  # DataSets (数据集) 模块
│   │   ├── __init__.py
│   │   ├── client.py              # 客户端 DataSet 操作 (浏览/读取/创建/删除)
│   │   └── server.py              # 服务端 DataSet 操作 (注册/管理)
│   │
│   ├── datamodels/                # DataModels (数据模型) 模块
│   │   ├── __init__.py
│   │   ├── discoverer.py          # 模型发现 (浏览 LD/LN/DO/DA)
│   │   ├── exporter.py            # 模型导出 (JSON/CSV/XML/ICD)
│   │   └── builder.py             # 服务端模型构建 (动态创建 IedModel)
│   │
│   └── files/                     # Files (文件服务) 模块
│       ├── __init__.py
│       ├── client.py              # 客户端文件操作 (获取文件列表/下载文件)
│       └── manager.py             # 文件服务管理器
│
├── client.py                      # IEC61850Client 门面类 (组合各模块)
├── server.py                      # IEC61850Server 门面类 (组合各模块)
└── _logging.py                    # 日志配置 (原 log.py)
```

### 3.2 架构图

```
┌──────────────────────────────────────────────────────────┐
│                    IEC61850Client (Facade)                │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐  │
│  │Connection│ │  Reader  │ │  Writer  │ │ PointRegistry│  │
│  └─────────┘ └──────────┘ └──────────┘ └─────────────┘  │
│  ┌──────────────── Plugin Registry ──────────────────┐   │
│  │ ┌───────┐ ┌────┐ ┌────────┐ ┌─────┐ ┌──────────┐ │   │
│  │ │ GOOSE │ │ SV │ │Reports │ │ Log │ │DataSets  │ │   │
│  │ └───────┘ └────┘ └────────┘ └─────┘ └──────────┘ │   │
│  │ ┌─────────────┐ ┌──────────┐ ┌──────────────────┐ │   │
│  │ │SettingGroups│ │DataModels│ │     Files        │ │   │
│  │ └─────────────┘ └──────────┘ └──────────────────┘ │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │   defs/   │  ← 所有模块共享
                    │ constants │
                    │ types     │
                    │ address   │
                    │ patterns  │
                    └───────────┘
```

---

## 4. 详细设计

### 4.1 defs/ - 公共定义包

#### 4.1.1 `defs/constants.py` - 常量与枚举

```python
"""IEC 61850 协议常量定义"""
from enum import IntEnum, StrEnum

# ===== pyiec61850 可用性检测 =====
try:
    from pyiec61850 import pyiec61850 as _iec61850
    HAS_IEC61850 = True
except ImportError:
    _iec61850 = None
    HAS_IEC61850 = False

# ===== 功能约束 (Functional Constraint) =====
class FunctionalConstraint(StrEnum):
    MX = "MX"  # 测量值
    ST = "ST"  # 状态
    CO = "CO"  # 控制
    CF = "CF"  # 配置
    DC = "DC"  # 描述
    GO = "GO"  # GOOSE
    SV = "SV"  # 替代值
    BL = "BL"  # 闭锁
    OR = "OR"  # 来源

# 运行时 FC 常量 (来自 pyiec61850，仅 HAS_IEC61850 时可用)
FC_MX = getattr(_iec61850, 'IEC61850_FC_MX', None)
FC_ST = getattr(_iec61850, 'IEC61850_FC_ST', None)
FC_CO = getattr(_iec61850, 'IEC61850_FC_CO', None)
FC_CF = getattr(_iec61850, 'IEC61850_FC_CF', None)
FC_DC = getattr(_iec61850, 'IEC61850_FC_DC', None)

# ===== IEC 61850 数据类型 =====
class IecType(StrEnum):
    FLOAT = "float"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    STRING = "string"
    TIMESTAMP = "timestamp"
    UNKNOWN = "unknown"

# ===== 遥测/遥信/遥控/遥调 类型 =====
class FrameType(IntEnum):
    YC = 0  # 遥测
    YX = 1  # 遥信
    YK = 2  # 遥控
    YT = 3  # 遥调

FRAME_TYPE_DESC = {
    FrameType.YC: "遥测(YC)",
    FrameType.YX: "遥信(YX)",
    FrameType.YK: "遥控(YK)",
    FrameType.YT: "遥调(YT)",
}

# ===== ACSI 类常量 =====
class AcsiClass(IntEnum):
    DATA_OBJECT = 0
    DATA_SET = 3
    BRCB = 5
    URCB = 6
    GOOSE = 9

# ===== FC -> FrameType 推断映射 =====
FC_TO_FRAME_TYPE: dict[str, FrameType] = {
    "MX": FrameType.YC,
    "ST": FrameType.YX,
    "CO": FrameType.YK,  # 遥控/遥调共用 CO
}

FRAME_TYPE_TO_FC: dict[FrameType, str] = {
    FrameType.YC: "MX",
    FrameType.YX: "ST",
    FrameType.YK: "CO",
    FrameType.YT: "CO",
}
```

#### 4.1.2 `defs/address.py` - 地址解析工具

```python
"""IEC 61850 地址解析与推断工具

统一地址解析、FC 推断、iec_type 推断逻辑，
供 Client/Server/ModelExporter 共用。
"""
from dataclasses import dataclass
from .constants import IecType, FrameType, FRAME_TYPE_TO_FC
from .da_patterns import DA_PATTERNS, EXTRA_DA_INFO, BDA_TYPE_MAP, DA_PATH_TO_FRAME_TYPE

@dataclass(frozen=True, slots=True)
class ParsedRef:
    """解析后的 IEC 61850 引用路径"""
    ld_inst: str
    ln_name: str
    do_name: str
    da_path: str

def is_full_ref(address) -> bool:
    """判断地址是否为完整引用路径 (包含 '/')"""
    return isinstance(address, str) and '/' in address

def parse_ref(address: str) -> ParsedRef | None:
    """解析完整引用路径，返回 ParsedRef 或 None"""
    ...

def infer_fc(address: str) -> str:
    """根据地址推断功能约束 (FC)"""
    ...

def infer_iec_type(address: str) -> IecType:
    """根据地址推断数据类型"""
    ...
```

#### 4.1.3 `defs/types.py` - 数据类

```python
"""IEC 61850 数据模型类型定义"""
from dataclasses import dataclass, field
from .constants import IecType, FrameType

@dataclass
class PointRef:
    """测点引用信息"""
    address: str           # 原始地址
    mms_ref: str           # MMS 引用路径
    fc: str                # 功能约束
    iec_type: IecType      # 数据类型
    frame_type: FrameType  # 帧类型
    code: str = ""         # 短编码
    name: str = ""         # 测点名称

@dataclass
class DAInfo:
    """数据属性 (DA) 信息"""
    name: str = ""
    path: str = ""
    fc: str = ""
    iec_type: IecType = IecType.UNKNOWN
    sub_das: list['DAInfo'] = field(default_factory=list)

@dataclass
class DOInfo:
    """数据对象 (DO) 信息"""
    name: str = ""
    ref: str = ""
    frame_type: FrameType = FrameType.YC
    das: list[DAInfo] = field(default_factory=list)

@dataclass
class DataSetInfo:
    """数据集 (DataSet) 信息"""
    ref: str = ""
    name: str = ""
    ld: str = ""
    ln: str = ""
    is_deletable: bool = False
    members: list[dict] = field(default_factory=list)

@dataclass
class GoCBInfo:
    """GOOSE 控制块信息"""
    go_cb_ref: str = ""
    go_id: str = ""
    app_id: int | None = None
    data_set_ref: str = ""
    conf_rev: int = 0
```

### 4.2 core/ - 核心连接与读写

#### 4.2.1 `core/connection.py` - 连接管理

```python
"""IEC 61850 MMS 连接生命周期管理

封装 IedConnection 的创建/连接/断开/重连，
提供连接状态监控和自动重连能力。
"""
class Iec61850Connection:
    """连接管理器
    
    职责:
    - IedConnection 创建与销毁
    - 连接/断开/重连
    - 连接状态心跳检测
    - LD 列表缓存
    """
    
    def __init__(self, ip: str, port: int, model_name: str = ""):
        ...
    
    def connect(self, auto_discover: bool = True) -> bool:
        ...
    
    def disconnect(self) -> None:
        ...
    
    def try_reconnect(self, max_retries: int = 3, interval: float = 5.0) -> bool:
        """自动重连 (指数退避)"""
        ...
    
    @property
    def is_connected(self) -> bool:
        ...
    
    @property
    def connection(self):
        """底层 IedConnection 对象 (供其他模块使用)"""
        ...
```

#### 4.2.2 `core/reader.py` / `core/writer.py` - 读写策略

```python
# core/reader.py
"""IEC 61850 数据读取

使用策略模式，按 IecType 分派不同的读取方法。
"""
from typing import Any, Protocol

class ReadStrategy(Protocol):
    """读取策略协议"""
    def read(self, conn, ref: str, fc) -> Any | None: ...
    def read_batch(self, conn, items: list, results: dict) -> None: ...

class FloatReader: ...
class BooleanReader: ...  # 含整数回退
class IntegerReader: ...
class StringReader: ...
class TimestampReader: ...
class AutoDetectReader: ...  # 依次尝试所有策略

# 策略注册表
READ_STRATEGIES: dict[IecType, ReadStrategy] = {
    IecType.FLOAT: FloatReader(),
    IecType.BOOLEAN: BooleanReader(),
    IecType.INTEGER: IntegerReader(),
    IecType.STRING: StringReader(),
    IecType.TIMESTAMP: TimestampReader(),
    IecType.UNKNOWN: AutoDetectReader(),
}

class Iec61850Reader:
    """数据读取器 (组合模式)"""
    def __init__(self, connection: Iec61850Connection, point_registry: PointRegistry):
        ...
    
    def read(self, address: str, fc: str = "") -> Any | None:
        ...
    
    def read_batch(self, addresses: list[str], fc_map: dict | None = None) -> dict[str, Any]:
        ...
```

### 4.3 plugins/ - 插件系统

#### 4.3.1 `plugins/base.py` - 插件协议

```python
"""IEC 61850 插件协议定义"""
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class Iec61850Plugin(Protocol):
    """IEC 61850 功能模块插件协议
    
    所有插件必须实现此协议，以便被 PluginRegistry 管理。
    """
    
    @property
    def name(self) -> str:
        """插件名称"""
        ...
    
    @property
    def available(self) -> bool:
        """插件是否可用 (依赖库是否安装)"""
        ...
    
    def initialize(self, connection: Any, **kwargs) -> None:
        """初始化插件 (注入连接等依赖)"""
        ...
    
    def shutdown(self) -> None:
        """关闭插件，释放资源"""
        ...
```

#### 4.3.2 `plugins/__init__.py` - 插件注册表

```python
"""IEC 61850 插件注册表"""
from typing import Type
from .base import Iec61850Plugin

class PluginRegistry:
    """插件注册与管理
    
    使用注册表模式 (Registry Pattern)，
    支持按需加载、热插拔、依赖检查。
    """
    
    def __init__(self):
        self._plugins: dict[str, Iec61850Plugin] = {}
        self._factories: dict[str, Type[Iec61850Plugin]] = {}
    
    def register(self, name: str, factory: Type[Iec61850Plugin]) -> None:
        """注册插件工厂"""
        ...
    
    def get(self, name: str) -> Iec61850Plugin | None:
        """获取插件实例 (懒创建)"""
        ...
    
    def get_all_available(self) -> dict[str, Iec61850Plugin]:
        """获取所有可用插件"""
        ...
    
    def initialize_all(self, connection, **kwargs) -> None:
        """初始化所有可用插件"""
        ...
    
    def shutdown_all(self) -> None:
        """关闭所有插件"""
        ...

# 全局注册表实例
registry = PluginRegistry()

# 注册内置插件
registry.register("goose", GoosePlugin)
registry.register("sv", SVPlugin)
registry.register("reports", ReportsPlugin)
registry.register("log", LogPlugin)
registry.register("setting_groups", SettingGroupsPlugin)
registry.register("datasets", DataSetsPlugin)
registry.register("datamodels", DataModelsPlugin)
registry.register("files", FilesPlugin)
```

### 4.4 client.py / server.py - 门面类

```python
# client.py
"""IEC 61850 MMS 客户端 (门面模式)

组合 core 和 plugins，提供统一的客户端 API。
保持与原有 IEC61850Client 接口兼容。
"""
from .core import Iec61850Connection, Iec61850Reader, Iec61850Writer
from .core import PointRegistry
from .plugins import PluginRegistry

class IEC61850Client:
    """IEC 61850 客户端门面
    
    通过组合模式将连接、读写、各插件功能统一暴露，
    同时保持原有 API 向后兼容。
    """
    
    def __init__(self, ip, port, model_name="EMS", ld_name="GenericLD"):
        self._connection = Iec61850Connection(ip, port, model_name)
        self._registry = PointRegistry(model_name, ld_name)
        self._reader = Iec61850Reader(self._connection, self._registry)
        self._writer = Iec61850Writer(self._connection, self._registry)
        self._plugins = PluginRegistry()
        
        # 初始化插件
        self._plugins.initialize_all(self._connection, registry=self._registry)
    
    # ===== 连接管理 (委托给 core/connection) =====
    def connect(self, auto_discover=True) -> bool: ...
    def disconnect(self): ...
    @property
    def is_connected(self) -> bool: ...
    
    # ===== 测点管理 (委托给 core/registry) =====
    def add_point(self, address, frame_type=0, fc="") -> str: ...
    
    # ===== 读写 (委托给 core/reader + core/writer) =====
    def read_point(self, address, fc="") -> Any: ...
    def read_points_batch(self, addresses, fc_map=None) -> dict: ...
    def write_point(self, address, value, fc="") -> bool: ...
    
    # ===== 插件功能 (按需暴露) =====
    @property
    def goose(self): return self._plugins.get("goose")
    @property
    def datasets(self): return self._plugins.get("datasets")
    @property
    def datamodels(self): return self._plugins.get("datamodels")
    @property
    def reports(self): return self._plugins.get("reports")
    @property
    def files(self): return self._plugins.get("files")
    
    # ===== 向后兼容的便捷方法 =====
    def discover_model(self) -> list[dict]: 
        """委托给 datamodels 插件"""
        ...
    def discover_datasets(self) -> list[dict]:
        """委托给 datasets 插件"""
        ...
```

---

## 5. 分阶段实施计划

### Phase 1: 基础拆分 (1-2 天)

**目标**: 消除冗余代码，建立 `defs/` 公共包

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 1.1 创建 `defs/constants.py` | P0 | 迁移 FC 常量、IEC_TYPE_*、FrameType 枚举 |
| 1.2 创建 `defs/ln_classes.py` | P0 | 迁移 iec61850_defs.py 内容 |
| 1.3 创建 `defs/da_patterns.py` | P0 | 迁移 _DA_PATTERNS, _EXTRA_DA_INFO, _SKIP_DA_NAMES, _BDA_TYPE_MAP 等 |
| 1.4 创建 `defs/address.py` | P0 | 统一 _is_full_ref, _parse_ref, infer_fc_from_address, infer_iec_type_from_address |
| 1.5 创建 `defs/types.py` | P0 | 定义 PointRef, DAInfo, DOInfo, DataSetInfo, GoCBInfo 等 dataclass |
| 1.6 更新 client/server/model_exporter 导入 | P0 | 从 defs 包导入，删除冗余定义 |

**验证**: 所有现有测试通过，无功能变更

### Phase 2: 核心拆分 (2-3 天)

**目标**: 将 client.py 的核心逻辑拆分到 `core/` 包

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 2.1 创建 `core/connection.py` | P0 | 抽取连接管理、重连、LD 缓存逻辑 |
| 2.2 创建 `core/mms_value.py` | P0 | 抽取 _mms_value_to_python 及类型转换 |
| 2.3 创建 `core/linked_list.py` | P0 | 抽取 _get_list_from_linked_list |
| 2.4 创建 `core/reader.py` | P0 | 抽取 read_point, read_points_batch, 各 _read_*_batch 方法 (策略模式) |
| 2.5 创建 `core/writer.py` | P0 | 抽取 write_point (策略模式) |
| 2.6 创建 `core/registry.py` | P1 | 抽取 PointRegistry (地址映射、FC/iec_type 缓存) |
| 2.7 重构 client.py 为门面类 | P0 | 委托给 core/ 各组件 |

**验证**: IEC61850Client 接口不变，所有功能正常

### Phase 3: 插件架构 (2-3 天)

**目标**: 建立插件系统，迁移功能模块

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 3.1 创建 `plugins/base.py` | P0 | 定义 Iec61850Plugin Protocol |
| 3.2 创建 `plugins/__init__.py` | P0 | 实现 PluginRegistry |
| 3.3 迁移 GOOSE 到 `plugins/goose/` | P0 | 重组 goose_publisher/subscriber/capture/manager |
| 3.4 迁移 DataSets 到 `plugins/datasets/` | P0 | 抽取 discover_datasets, browse_dataset_directory, read_dataset_values |
| 3.5 迁移 DataModels 到 `plugins/datamodels/` | P0 | 抽取 discover_model, model_exporter |
| 3.6 创建 Reports 插件骨架 | P1 | BRCB/URCB 操作封装 |
| 3.7 创建 SV 插件骨架 | P2 | SV 发布/订阅封装 |
| 3.8 创建 Log 插件骨架 | P2 | LCB 操作封装 |
| 3.9 创建 SettingGroups 插件骨架 | P2 | SGCB 操作封装 |
| 3.10 创建 Files 插件骨架 | P2 | 文件服务封装 |

**验证**: 插件按需加载，Client/Server 门面类 API 兼容

### Phase 4: Server 重构 (1-2 天)

**目标**: 重构 IEC61850Server，复用 defs/ 和 plugins/

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 4.1 抽取服务端模型构建到 `plugins/datamodels/builder.py` | P0 | 动态 IedModel 创建逻辑 |
| 4.2 抽取服务端 DataSet 到 `plugins/datasets/server.py` | P0 | 服务端 DataSet 注册 |
| 4.3 重构 server.py 为门面类 | P0 | 委托给 datamodels/builder + datasets/server |
| 4.4 统一 Server 的 GOOSE 集成 | P1 | 通过 goose 插件管理 |

**验证**: IEC61850Server 接口不变，所有功能正常

### Phase 5: 鲁棒性增强 (1-2 天)

**目标**: 增强错误处理、重试机制、类型安全

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 5.1 连接自动重连 | P0 | 指数退避重连，连接丢失自动恢复 |
| 5.2 统一异常体系 | P0 | 定义 Iec61850Error, ConnectionError, ReadError, WriteError 等 |
| 5.3 读取操作重试 | P1 | 单次读取失败自动重试 (可配置) |
| 5.4 连接状态心跳 | P1 | 定期检测连接有效性 |
| 5.5 类型注解完善 | P1 | 所有公开 API 添加完整类型注解 |
| 5.6 py.typed 标记 | P2 | 支持 PEP 561 类型检查 |

**验证**: 异常场景 (断连/超时/错误数据) 均有优雅处理

### Phase 6: 测试与文档 (1-2 天)

**目标**: 完善单元测试和文档

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 6.1 defs/ 单元测试 | P0 | 地址解析、FC 推断、iec_type 推断 |
| 6.2 core/ 单元测试 | P0 | 连接管理、读写策略 (mock pyiec61850) |
| 6.3 plugins/ 单元测试 | P1 | 各插件独立测试 |
| 6.4 集成测试 | P1 | Client/Server 端到端测试 |
| 6.5 更新 API 文档 | P2 | 模块接口文档 |

---

## 6. 设计模式清单

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **Facade** | client.py, server.py | 统一入口，隐藏内部复杂性 |
| **Strategy** | core/reader.py, core/writer.py | 按 IecType 分派读写方法 |
| **Registry** | plugins/__init__.py | 插件注册与按需加载 |
| **Protocol (结构化子类型)** | plugins/base.py | Python 3.8+ 鸭子类型约束 |
| **Dataclass (值对象)** | defs/types.py | 不可变数据结构 |
| **Enum** | defs/constants.py | 类型安全常量 |
| **Composition** | IEC61850Client | 组合优于继承 |
| **Lazy Initialization** | plugins, model_exporter | 按需创建，减少启动开销 |
| **Context Manager** | core/connection.py | `with` 语句管理连接生命周期 |

---

## 7. 向后兼容策略

重构过程中必须保证 **100% API 向后兼容**:

1. **IEC61850Client** 所有公开方法签名不变
2. **IEC61850Server** 所有公开方法签名不变
3. **导入路径兼容**: `from src.proto.iec61850.iec61850_client import IEC61850Client` 仍然有效
4. **内部模块导入兼容**: `iec61850_model_exporter.py` 的旧导入路径通过 `defs/` 重导出保持可用
5. **常量兼容**: `IEC_TYPE_FLOAT` 等旧常量名在 `defs/constants.py` 中作为 `IecType.FLOAT` 的别名保留

```python
# defs/constants.py - 向后兼容别名
IEC_TYPE_FLOAT = IecType.FLOAT
IEC_TYPE_BOOLEAN = IecType.BOOLEAN
IEC_TYPE_INTEGER = IecType.INTEGER
IEC_TYPE_STRING = IecType.STRING
IEC_TYPE_TIMESTAMP = IecType.TIMESTAMP
IEC_TYPE_UNKNOWN = IecType.UNKNOWN
```

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 重构引入回归 bug | 中 | 高 | 每个阶段完成后运行全量测试 |
| pyiec61850 API 差异 | 低 | 高 | 保留 try/except 多版本兼容逻辑 |
| 插件间依赖复杂化 | 低 | 中 | 插件间通过事件/接口通信，禁止直接引用 |
| 迁移周期过长 | 中 | 中 | 分阶段增量交付，每阶段独立可用 |
| 循环导入 | 中 | 低 | 严格依赖方向: defs ← core ← plugins ← facade |

---

## 9. 验收标准

- [ ] `iec61850_client.py` 从 2307 行降至 < 300 行 (门面类)
- [ ] `iec61850_server.py` 从 ~1800 行降至 < 300 行 (门面类)
- [ ] 零冗余代码: `_is_full_ref`, `_parse_ref`, FC 常量等只存在一处
- [ ] 所有 8 个插件模块 (GOOSE/SV/Reports/Log/SettingGroups/DataSets/DataModels/Files) 有独立文件夹
- [ ] `defs/` 包含所有共享定义，无反向依赖
- [ ] 现有所有 API 调用无需修改即可运行
- [ ] 连接断开自动重连功能可用
- [ ] 统一异常体系，无裸 `except: pass`
- [ ] 核心模块单元测试覆盖率 > 80%
