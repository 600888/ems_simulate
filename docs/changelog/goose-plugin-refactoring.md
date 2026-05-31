# GOOSE 模块插件化重构计划

> 版本: 1.0  
> 日期: 2026-05-31  
> 状态: 规划中  
> 关联: [iec61850-refactoring-plan.md](./iec61850-refactoring-plan.md) Phase 3.3

---

## 1. 概述

将 GOOSE 模块从当前的"薄包装层"改造为完整、规范的 IEC61850 插件实现，遵循项目已建立的 `Iec61850Plugin` 协议和 `PluginRegistry` 机制，采用现代 Python 设计模式，与 Reports、Files、DataSets 等成熟插件对齐。

### 1.1 当前状态

GOOSE 模块目前以 4 个独立文件存在于 `src/proto/iec61850/` 顶层目录：

| 文件 | 行数 | 职责 |
|------|------|------|
| `goose_publisher.py` | ~408 | GOOSE 发布者封装 |
| `goose_subscriber.py` | ~390 | GOOSE 接收器/订阅者封装 |
| `goose_capture.py` | ~560 | GOOSE 原始报文捕获引擎 |
| `goose_manager.py` | ~753 | GOOSE 资源管理器 (Singleton) |

而 `plugins/goose/__init__.py` 仅 71 行，是一个最小化的协议适配器，通过懒加载引用上述 4 个文件，未真正内聚为插件。

### 1.2 核心问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **插件徒有其表** | 🔴 高 | `GoosePlugin` 仅做 `from ...goose_manager import GooseManager` 的懒加载转发，未内聚业务逻辑 |
| **Manager 与 Plugin 职责重叠** | 🔴 高 | `GooseManager` 承担了插件应承担的 Publisher/Receiver 生命周期管理，但又在插件之外独立存在 |
| **全局单例反模式** | 🟡 中 | `get_goose_manager()` 全局单例绕过插件系统，无法被 `PluginRegistry.shutdown_all()` 管理 |
| **类型不安全** | 🟡 中 | `GooseDataSetEntry` 使用裸 `__init__` 而非 dataclass；状态字符串 `"init"` 等未枚举化 |
| **MMS 常量重复** | 🟡 中 | `goose_subscriber.py` 中硬编码 `MMS_BOOLEAN = 0` 等常量，与 `defs/constants.py` 重复 |
| **线程模型耦合** | 🟡 中 | Publisher 重发线程和 Receiver 监控线程直接 `threading.Thread` 裸创建，缺乏统一的线程生命周期管理 |
| **持久化耦合** | 🟡 中 | `GooseManager` 直接依赖 `goose_publisher_dao`，DAO 操作与业务逻辑混合 |
| **缺少类型注解** | 🟢 低 | 部分公开方法缺少返回类型注解 |

---

## 2. 重构目标

1. **完整插件化**: GOOSE 作为一等公民插件，业务逻辑内聚于 `plugins/goose/` 包内
2. **协议合规**: 严格实现 `Iec61850Plugin` 协议，生命周期由 `PluginRegistry` 统一管理
3. **现代 Python**: dataclass、enum、Protocol、组合模式、策略模式
4. **关注点分离**: Publisher/Receiver/Capture/Manager 各自独立，通过门面类聚合
5. **消除全局单例**: `GooseManager` 不再是全局单例，改为插件内部实例
6. **类型安全**: 完整类型注解，`dataclass(frozen=True)` 不可变值对象，`StrEnum` 状态枚举
7. **可测试性**: 每个子模块可独立 mock 和单元测试

---

## 3. 目标架构

### 3.1 目录结构

```
src/proto/iec61850/plugins/goose/
├── __init__.py           # GoosePlugin 门面类 (实现 Iec61850Plugin 协议)
├── types.py              # 数据类型定义 (dataclass + enum)
├── publisher.py          # GoosePublisher 发布者
├── subscriber.py         # GooseReceiver 接收器 + GooseSubscription 订阅
├── capture.py            # GooseCaptureEngine 报文捕获引擎
├── manager.py            # GooseResourceManager 资源管理器 (非全局单例)
└── persistence.py        # 持久化适配层 (DAO 调用隔离)
```

### 3.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     GoosePlugin (门面)                        │
│  implements Iec61850Plugin                                    │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              GooseResourceManager                        │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │ │
│  │  │  Publisher    │  │  Receiver    │  │  Capture     │ │ │
│  │  │  (per-GoCB)  │  │  (per-IF)    │  │  Engine      │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────┐  ┌────────────────────────────────┐ │
│  │  PersistenceAdapter │  │  GooseEventEmitter (可选)       │ │
│  │  (DAO 隔离层)       │  │  (事件通知, 替代裸回调)         │ │
│  └─────────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
   defs/constants.py   defs/types.py      core/connection.py
   (HAS_IEC61850,      (GoCBInfo,         (Iec61850Connection)
    MMS 常量)           DataSetInfo)
```

### 3.3 依赖方向

```
defs/ ← core/ ← plugins/goose/ ← client.py (门面)
                    ↑
              plugins/base.py (协议)
```

严格禁止: `defs/` → `plugins/`、`plugins/goose/` → `client.py`

---

## 4. 详细设计

### 4.1 `types.py` — 类型定义

使用 `dataclass` 和 `StrEnum` 替代裸类和字符串常量：

```python
"""GOOSE 插件数据类型定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, IntEnum
from typing import Any


# ===== 枚举类型 =====

class GooseState(StrEnum):
    """GOOSE 订阅状态"""
    INIT = "init"
    CONNECTED = "connected"
    LOST = "lost"
    ERROR = "error"


class IecDataType(StrEnum):
    """IEC 61850 数据类型标识"""
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BITSTRING = "bitstring"
    TIMESTAMP = "timestamp"


class MmsType(IntEnum):
    """MMS 数据类型常量 (与 pyiec61850 对应)"""
    BOOLEAN = 0
    BIT_STRING = 1
    INTEGER = 2
    UNSIGNED = 3
    FLOAT = 4
    VISIBLE_STRING = 10
    UTC_TIME = 17


# ===== 常量 =====

GOOSE_MULTICAST_MAC_PREFIX = [0x01, 0x0C, 0xCD, 0x01, 0x00]
DEFAULT_TIME_ALLOWED_TO_LIVE = 1000
DEFAULT_CONF_REV = 1
DEFAULT_ST_NUM = 1
DEFAULT_SQ_NUM = 0

GOOSE_STATE_COLOR: dict[GooseState, str] = {
    GooseState.INIT: "#909399",
    GooseState.CONNECTED: "#67C23A",
    GooseState.LOST: "#E6A23C",
    GooseState.ERROR: "#F56C6C",
}


# ===== 数据类 =====

@dataclass(frozen=True, slots=True)
class GooseDataSetEntry:
    """GOOSE 数据集条目 (不可变值对象)
    
    修改时创建新实例，而非原地修改 value 字段。
    """
    name: str
    value: Any = False
    iec_type: IecDataType = IecDataType.BOOLEAN


@dataclass
class GooseSubscriptionInfo:
    """GOOSE 订阅信息 (可变状态)"""
    go_cb_ref: str
    app_id: int | None = None
    dst_mac: list[int] | None = None
    description: str = ""
    go_id: str = ""
    data_set_ref: str = ""
    conf_rev: int = 0
    st_num: int = 0
    sq_num: int = 0
    time_allowed_to_live: int = 0
    timestamp: int = 0
    state: GooseState = GooseState.INIT
    last_update: float = 0.0
    data_values: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "go_cb_ref": self.go_cb_ref,
            "app_id": self.app_id,
            "go_id": self.go_id,
            "data_set_ref": self.data_set_ref,
            "conf_rev": self.conf_rev,
            "st_num": self.st_num,
            "sq_num": self.sq_num,
            "time_allowed_to_live": self.time_allowed_to_live,
            "timestamp": self.timestamp,
            "state": self.state.value,
            "last_update": self.last_update,
            "description": self.description,
            "dst_mac": ":".join(f"{b:02X}" for b in self.dst_mac) if self.dst_mac else "",
            "data_values": self.data_values,
        }


@dataclass(frozen=True, slots=True)
class PublisherConfig:
    """GOOSE Publisher 创建配置 (不可变)"""
    interface: str = "eth0"
    go_cb_ref: str = ""
    go_id: str = ""
    data_set_ref: str = ""
    app_id: int = 0x0001
    conf_rev: int = DEFAULT_CONF_REV
    time_allowed_to_live: int = DEFAULT_TIME_ALLOWED_TO_LIVE
    dst_mac: list[int] | None = None
    vlan_id: int = 0
    vlan_prio: int = 4
    simulation: bool = True


@dataclass(frozen=True, slots=True)
class ReceiverConfig:
    """GOOSE Receiver 创建配置 (不可变)"""
    interface: str = "eth0"
```

**设计要点**:
- `GooseDataSetEntry` 使用 `frozen=True` + `slots=True`，修改值时创建新实例
- `GooseState` 使用 `StrEnum`，序列化时 `.value` 产出 `"init"` 等字符串，兼容前端
- `MmsType` 替代 `goose_subscriber.py` 中硬编码的 `MMS_BOOLEAN = 0` 等常量
- `PublisherConfig` / `ReceiverConfig` 作为创建参数的不可变值对象

### 4.2 `publisher.py` — GOOSE 发布者

重构核心改动：
- 使用 `PublisherConfig` 不可变配置
- `GooseDataSetEntry` 改为 frozen dataclass，`update_entry` 返回新实例
- 提取 `_IecApiAdapter` 封装 `_call_iec` 的 API 调用兼容逻辑
- 线程管理统一为 `_RetransmitWorker`

```python
"""GOOSE 发布者 - 基于 pyiec61850 实现 GOOSE 报文发布"""
from __future__ import annotations

import threading
from typing import Any

from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import (
    GooseDataSetEntry, IecDataType, PublisherConfig,
    GOOSE_MULTICAST_MAC_PREFIX, DEFAULT_ST_NUM, DEFAULT_SQ_NUM,
)


class GoosePublisher:
    """IEC 61850 GOOSE 发布者
    
    管理单个 GoCB 的报文发布、数据集、序号、定时重发。
    线程安全: _lock 保护 _entries、_st_num、_sq_num。
    """

    def __init__(self, config: PublisherConfig):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 GOOSE Publisher")
        
        self._config = config
        self._entries: list[GooseDataSetEntry] = []
        self._st_num: int = DEFAULT_ST_NUM
        self._sq_num: int = DEFAULT_SQ_NUM
        
        # 计算默认组播 MAC
        self._dst_mac = config.dst_mac or (
            GOOSE_MULTICAST_MAC_PREFIX
            + [(config.app_id >> 8) & 0xFF, config.app_id & 0xFF]
        )
        
        # 底层状态
        self._publisher: Any = None
        self._comm_params: Any = None
        self._is_running = False
        self._is_created = False
        
        # 定时重发
        self._retransmit_interval = config.time_allowed_to_live / 2000.0
        self._retransmit_stop = threading.Event()
        self._retransmit_thread: threading.Thread | None = None
        
        # 线程锁
        self._lock = threading.Lock()

    # ===== 配置属性 (只读) =====

    @property
    def config(self) -> PublisherConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def st_num(self) -> int:
        return self._st_num

    @property
    def sq_num(self) -> int:
        return self._sq_num

    # ===== 数据集管理 =====

    def add_entry(self, entry: GooseDataSetEntry) -> None:
        """添加数据集条目 (同名检查)"""
        with self._lock:
            if any(e.name == entry.name for e in self._entries):
                raise ValueError(f"数据集条目名称已存在: {entry.name}")
            self._entries.append(entry)
            self._is_created = False

    def remove_entry(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._entries):
                self._entries.pop(index)
                self._is_created = False

    def update_entry(self, index: int, value: Any) -> bool:
        """更新条目值，返回 True 表示值有变化 (触发 stNum 递增)"""
        changed = False
        with self._lock:
            if 0 <= index < len(self._entries):
                old_entry = self._entries[index]
                if old_entry.value != value:
                    self._entries[index] = GooseDataSetEntry(
                        name=old_entry.name, value=value, iec_type=old_entry.iec_type
                    )
                    self._st_num += 1
                    self._sq_num = 0
                    changed = True
        if changed and self._is_running:
            self.publish()
        return changed

    def get_entries(self) -> list[dict[str, Any]]:
        return [
            {"index": i, "name": e.name, "value": e.value, "iec_type": e.iec_type.value}
            for i, e in enumerate(self._entries)
        ]

    # ===== 生命周期 =====

    def start(self) -> bool: ...
    def stop(self) -> None: ...
    def publish(self) -> bool: ...
    def get_status(self) -> dict[str, Any]: ...
```

### 4.3 `subscriber.py` — GOOSE 接收器

重构核心改动：
- `GooseSubscription` → `GooseSubscriptionInfo` (dataclass)
- 状态字符串 → `GooseState` 枚举
- MMS 常量 → `MmsType` 枚举
- 提取 `_DataSetParser` 策略类处理数据集值解析

```python
"""GOOSE 接收器/订阅者 - 基于 pyiec61850 实现 GOOSE 报文接收"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import GooseState, GooseSubscriptionInfo, MmsType, ReceiverConfig

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class GooseReceiver:
    """IEC 61850 GOOSE 接收器
    
    管理单个网络接口上的 GOOSE 报文接收和多个订阅。
    """

    def __init__(self, config: ReceiverConfig):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 GOOSE Receiver")
        
        self._config = config
        self._subscriptions: dict[str, GooseSubscriptionInfo] = {}
        self._is_running = False
        self._callback: Callable[[dict[str, Any]], None] | None = None
        self._lock = threading.Lock()
        
        # 底层
        self._receiver: Any = None
        
        # 状态监控
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    # ... (add_subscription, remove_subscription, start, stop 等)
```

### 4.4 `capture.py` — GOOSE 报文捕获引擎

重构核心改动：
- `GooseCapturedPacket` → frozen dataclass
- 提取 `_GoosePduParser` 处理 ASN.1 BER-TLV 解析
- 提取 `_RawSocketProvider` 封装跨平台原始套接字创建

```python
"""GOOSE 报文捕获引擎 - 原始套接字抓包 + ASN.1 解析"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from ...log import log
from .types import GooseState, MmsType


@dataclass(frozen=True, slots=True)
class CapturedPacket:
    """单条捕获的 GOOSE 报文 (不可变值对象)"""
    timestamp: datetime
    go_cb_ref: str = ""
    go_id: str = ""
    app_id: int = 0
    st_num: int = 0
    sq_num: int = 0
    conf_rev: int = 0
    simulation: bool = False
    time_allowed_to_live: int = 0
    nds_com: bool = False
    num_entries: int = 0
    data_values: tuple[dict[str, Any], ...] = ()
    raw_bytes: bytes = b""
    interface: str = ""


class GooseCaptureEngine:
    """GOOSE 报文捕获引擎
    
    功能:
    - 跨平台原始套接字抓包
    - GOOSE PDU (ASN.1 BER-TLV) 解析
    - 环形缓冲区存储 (deque)
    - 按 APPID/GoCBRef 过滤
    """
    ...
```

### 4.5 `manager.py` — GOOSE 资源管理器

重构核心改动：
- 不再是全局单例，由 `GoosePlugin` 内部持有
- 持久化逻辑委托给 `PersistenceAdapter`
- Server 集成通过回调/接口而非直接依赖

```python
"""GOOSE 资源管理器 - 管理 Publisher/Receiver/Capture 的完整生命周期"""
from __future__ import annotations

from typing import Any, Callable

from ...log import log
from .types import PublisherConfig, ReceiverConfig, GooseDataSetEntry, IecDataType
from .publisher import GoosePublisher
from .subscriber import GooseReceiver, GooseSubscriptionInfo
from .capture import GooseCaptureEngine
from .persistence import PersistenceAdapter


class GooseResourceManager:
    """GOOSE 资源管理器
    
    管理:
    - _publishers: dict[str, GoosePublisher]   # go_cb_ref -> publisher
    - _receivers: dict[str, GooseReceiver]     # interface -> receiver  
    - _capture_engines: dict[str, GooseCaptureEngine]  # interface -> engine
    
    不再是全局单例，由 GoosePlugin 持有实例。
    """

    def __init__(self, persistence: PersistenceAdapter | None = None):
        self._publishers: dict[str, GoosePublisher] = {}
        self._receivers: dict[str, GooseReceiver] = {}
        self._capture_engines: dict[str, GooseCaptureEngine] = {}
        self._persistence = persistence or PersistenceAdapter()

    # ===== Publisher 管理 =====
    def create_publisher(self, config: PublisherConfig, ...) -> dict[str, Any] | None: ...
    def list_publishers(self) -> list[dict[str, Any]]: ...
    def get_publisher_status(self, publisher_id: str) -> dict[str, Any] | None: ...
    def update_publisher(self, publisher_id: str, ...) -> dict[str, Any] | None: ...
    def delete_publisher(self, publisher_id: str, delete_from_db: bool = False) -> bool: ...
    def start_publisher(self, publisher_id: str) -> bool: ...
    def stop_publisher(self, publisher_id: str) -> bool: ...
    def publish_now(self, publisher_id: str) -> bool: ...

    # ===== Publisher 数据集管理 =====
    def add_publisher_entry(self, publisher_id: str, entry: GooseDataSetEntry) -> dict[str, Any] | None: ...
    def update_publisher_entry(self, publisher_id: str, index: int, value: Any) -> bool | None: ...
    def remove_publisher_entry(self, publisher_id: str, index: int) -> bool: ...

    # ===== Receiver 管理 =====
    def create_receiver(self, config: ReceiverConfig, ...) -> dict[str, Any] | None: ...
    def list_receivers(self) -> list[dict[str, Any]]: ...
    def get_receiver_status(self, receiver_id: str) -> dict[str, Any] | None: ...
    def delete_receiver(self, receiver_id: str) -> bool: ...
    def start_receiver(self, receiver_id: str) -> bool: ...
    def stop_receiver(self, receiver_id: str) -> bool: ...

    # ===== Receiver 订阅管理 =====
    def add_subscription(self, receiver_id: str, ...) -> dict[str, Any] | None: ...
    def remove_subscription(self, receiver_id: str, go_cb_ref: str) -> bool: ...

    # ===== Capture 管理 =====
    def start_capture(self, interface: str, ...) -> dict[str, Any] | None: ...
    def stop_capture(self, interface: str) -> bool: ...
    def get_captured_packets(self, interface: str, ...) -> list[dict[str, Any]]: ...

    # ===== 全局管理 =====
    def stop_all(self) -> None: ...
    def get_all_status(self) -> dict[str, Any]: ...

    # ===== 持久化 =====
    def save_to_db(self, channel_id: int, go_cb_ref: str) -> bool: ...
    def load_from_db(self, channel_id: int | None = None, ...) -> int: ...
```

### 4.6 `persistence.py` — 持久化适配层

将 DAO 调用从 Manager 中隔离，支持测试时 mock 替换：

```python
"""GOOSE 持久化适配层 - 隔离 DAO 调用，便于测试"""
from __future__ import annotations

from typing import Any, Protocol


class PersistenceBackend(Protocol):
    """持久化后端协议 (可替换为 mock 实现)"""
    
    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None: ...
    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool: ...
    def delete_by_channel(self, channel_id: int) -> int: ...
    def get_by_channel(self, channel_id: int) -> list[dict[str, Any]]: ...
    def get_all(self) -> list[dict[str, Any]]: ...
    def get_all_pure_datasets(self) -> list[dict[str, Any]]: ...


class DaoPersistenceBackend:
    """默认实现: 委托给 GoosePublisherDao"""
    
    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao
        return GoosePublisherDao.save_publisher(channel_id, status)
    
    # ... 其他方法


class PersistenceAdapter:
    """持久化适配器"""
    
    def __init__(self, backend: PersistenceBackend | None = None):
        self._backend = backend or DaoPersistenceBackend()
    
    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        return self._backend.save_publisher(channel_id, status)
    
    # ... 委托方法
```

### 4.7 `__init__.py` — GoosePlugin 门面类

完整实现 `Iec61850Plugin` 协议，替代当前的薄包装层：

```python
"""GOOSE 插件 - IEC 61850 GOOSE 功能模块

管理 GOOSE 报文的发布 (Publisher)、订阅 (Receiver)、
捕获 (Capture) 的完整生命周期。

模块结构:
- types.py        — 数据类型定义 (dataclass + enum)
- publisher.py    — GoosePublisher 发布者
- subscriber.py   — GooseReceiver 接收器 + GooseSubscription 订阅
- capture.py      — GooseCaptureEngine 报文捕获引擎
- manager.py      — GooseResourceManager 资源管理器
- persistence.py  — 持久化适配层 (DAO 调用隔离)
"""
from __future__ import annotations

from typing import Any

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850
from ...log import log

from .types import (
    GooseDataSetEntry, GooseState, IecDataType,
    PublisherConfig, ReceiverConfig,
)
from .manager import GooseResourceManager
from .persistence import PersistenceAdapter


class GoosePlugin:
    """GOOSE 插件 — 实现 Iec61850Plugin 协议
    
    作为 GOOSE 功能的门面，对外暴露 Publisher/Receiver/Capture 的
    完整管理 API，对内通过 GooseResourceManager 协调各组件。
    """

    def __init__(self):
        self._connection: Any = None
        self._manager: GooseResourceManager | None = None
        self._initialized = False

    # ===== Iec61850Plugin 协议实现 =====

    @property
    def name(self) -> str:
        return "goose"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """初始化 GOOSE 插件
        
        Args:
            connection: Iec61850Connection 实例
            **kwargs: 支持 persistence (PersistenceAdapter 实例)
        """
        self._connection = connection
        persistence = kwargs.get("persistence", PersistenceAdapter())
        self._manager = GooseResourceManager(persistence=persistence)
        self._initialized = True
        log.info("GOOSE 插件已初始化")

    def shutdown(self) -> None:
        """关闭 GOOSE 插件，停止所有资源"""
        if self._manager:
            self._manager.stop_all()
        self._connection = None
        self._manager = None
        self._initialized = False
        log.info("GOOSE 插件已关闭")

    # ===== 门面属性 =====

    @property
    def manager(self) -> GooseResourceManager | None:
        """获取资源管理器实例"""
        return self._manager

    # ===== 便捷方法 (委托给 manager) =====

    def create_publisher(self, **kwargs) -> dict[str, Any] | None:
        """创建 GOOSE Publisher"""
        if not self._manager:
            return None
        config = PublisherConfig(**kwargs)
        return self._manager.create_publisher(config, ...)

    def create_subscriber(self, **kwargs) -> dict[str, Any] | None:
        """创建 GOOSE Receiver"""
        if not self._manager:
            return None
        config = ReceiverConfig(**kwargs)
        return self._manager.create_receiver(config, ...)

    # ... 其他便捷方法按需暴露
```

---

## 5. 设计模式清单

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **Protocol (结构化子类型)** | `Iec61850Plugin`, `PersistenceBackend` | 鸭子类型约束，无需显式继承 |
| **Facade** | `GoosePlugin` | 统一入口，隐藏 Manager/子模块复杂性 |
| **Registry** | `PluginRegistry` | 插件注册与按需加载 (已存在) |
| **Adapter** | `PersistenceAdapter` + `PersistenceBackend` | 隔离 DAO 依赖，支持 mock 替换 |
| **Value Object** | `GooseDataSetEntry(frozen)`, `PublisherConfig(frozen)` | 不可变数据结构 |
| **Enum** | `GooseState`, `IecDataType`, `MmsType` | 类型安全常量 |
| **Strategy** | `_IecApiAdapter` (publisher.py) | 封装 pyiec61850 API 版本差异 |
| **Composition** | `GoosePlugin` → `GooseResourceManager` → 各子模块 | 组合优于继承 |
| **Context Manager** | `GoosePublisher` / `GooseReceiver` (可选增强) | `with` 语句管理底层 C 资源 |

---

## 6. 分阶段实施计划

### Phase 1: 类型提取与基础重构 (0.5 天)

**目标**: 建立类型基础，消除硬编码常量

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 1.1 创建 `plugins/goose/types.py` | P0 | 定义 `GooseState`, `IecDataType`, `MmsType`, `GooseDataSetEntry`, `PublisherConfig`, `ReceiverConfig` |
| 1.2 创建 `plugins/goose/persistence.py` | P0 | 定义 `PersistenceBackend` Protocol + `DaoPersistenceBackend` |
| 1.3 验证 | P0 | 类型定义可被其他模块导入 |

### Phase 2: Publisher 重构 (1 天)

**目标**: 将 `goose_publisher.py` 迁移到插件包内

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 2.1 创建 `plugins/goose/publisher.py` | P0 | 基于 `PublisherConfig` 和 `GooseDataSetEntry` 重写 |
| 2.2 提取 `_IecApiAdapter` | P1 | 封装 `_call_iec` 版本兼容逻辑 |
| 2.3 删除旧文件 `goose_publisher.py` | P0 | 全局搜索确认无直接导入后删除 |
| 2.4 验证 | P0 | GoosePublisher 功能不变，Web API 正常 |

### Phase 3: Subscriber 重构 (1 天)

**目标**: 将 `goose_subscriber.py` 迁移到插件包内

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 3.1 创建 `plugins/goose/subscriber.py` | P0 | 基于 `GooseState`, `MmsType`, `GooseSubscriptionInfo` 重写 |
| 3.2 删除旧文件 `goose_subscriber.py` | P0 | 全局搜索确认无直接导入后删除 |
| 3.3 验证 | P0 | GooseReceiver 功能不变 |

### Phase 4: Capture 重构 (0.5 天)

**目标**: 将 `goose_capture.py` 迁移到插件包内

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 4.1 创建 `plugins/goose/capture.py` | P0 | `GooseCapturedPacket` → `CapturedPacket` dataclass |
| 4.2 删除旧文件 `goose_capture.py` | P0 | 全局搜索确认无直接导入后删除 |
| 4.3 验证 | P1 | 抓包功能正常 |

### Phase 5: Manager 重构 (1 天)

**目标**: 将 `GooseManager` 迁移到插件包内，消除全局单例

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 5.1 创建 `plugins/goose/manager.py` | P0 | `GooseResourceManager` 使用 `PersistenceAdapter`，不再直接依赖 DAO |
| 5.2 消除全局单例 | P0 | 删除 `get_goose_manager()` 函数和 `_goose_manager` 全局变量，由 `GoosePlugin` 内部持有 |
| 5.3 删除旧文件 `goose_manager.py` | P0 | 全局搜索更新所有 `from ...goose_manager import` 引用后删除 |
| 5.4 更新 `src/web/app.py` | P0 | 从 `app.state.goose_manager` 切换到通过插件系统获取 |
| 5.5 更新 `src/web/api/channel/goose.py` | P0 | 路由层通过插件系统访问 GOOSE 功能 |
| 5.6 全局搜索更新所有外部引用 | P0 | 搜索 `GooseManager`, `get_goose_manager`, `goose_publisher`, `goose_subscriber`, `goose_capture` 的所有导入 |
| 5.7 验证 | P0 | Web API 全部端点正常 |

### Phase 6: Plugin 门面类实现 (0.5 天)

**目标**: 将 `GoosePlugin` 从薄包装升级为完整插件

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 6.1 重写 `plugins/goose/__init__.py` | P0 | `GoosePlugin` 完整实现 `Iec61850Plugin` 协议 |
| 6.2 验证 `PluginRegistry` 集成 | P0 | `client.goose` 属性可用，`initialize_all` / `shutdown_all` 正确管理 GOOSE |

### Phase 7: 清理与测试 (0.5 天)

**目标**: 确认无残留，添加测试

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 7.1 添加 types.py 单元测试 | P0 | 枚举序列化、dataclass 构建 |
| 7.2 添加 publisher.py 单元测试 | P1 | mock pyiec61850 测试数据集管理、序号递增 |
| 7.3 添加 subscriber.py 单元测试 | P1 | mock 回调、状态机转换 |
| 7.4 添加 persistence.py 单元测试 | P1 | mock DAO 测试持久化 |
| 7.5 确认无残留旧导入 | P0 | 全局搜索确认无任何文件引用旧路径 |

---

## 7. 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `plugins/goose/types.py` | 类型定义 (dataclass + enum) |
| `plugins/goose/persistence.py` | 持久化适配层 |
| `plugins/goose/publisher.py` | GOOSE 发布者 (从 `goose_publisher.py` 迁移) |
| `plugins/goose/subscriber.py` | GOOSE 接收器 (从 `goose_subscriber.py` 迁移) |
| `plugins/goose/capture.py` | GOOSE 捕获引擎 (从 `goose_capture.py` 迁移) |
| `plugins/goose/manager.py` | GOOSE 资源管理器 (从 `goose_manager.py` 迁移) |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `plugins/goose/__init__.py` | 从薄包装改为完整 `GoosePlugin` 实现 |
| `src/web/app.py` | startup 中从插件系统获取 GOOSE 功能，移除 `app.state.goose_manager` |
| `src/web/api/channel/goose.py` | 路由层改用插件系统访问 |
| 所有引用旧 GOOSE 文件的模块 | 更新导入路径到 `plugins/goose/` |

### 删除文件

| 文件 | 说明 |
|------|------|
| `src/proto/iec61850/goose_publisher.py` | 已迁移到 `plugins/goose/publisher.py` |
| `src/proto/iec61850/goose_subscriber.py` | 已迁移到 `plugins/goose/subscriber.py` |
| `src/proto/iec61850/goose_capture.py` | 已迁移到 `plugins/goose/capture.py` |
| `src/proto/iec61850/goose_manager.py` | 已迁移到 `plugins/goose/manager.py`，全局单例一并消除 |

### 不变文件

| 文件 | 说明 |
|------|------|
| `src/web/api/schemas/goose.py` | Pydantic Schema 不变 |
| `front/src/api/gooseApi.ts` | 前端 API 层不变 |
| `front/src/components/goose/` | 前端组件不变 |

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 重构引入回归 bug | 中 | 高 | 分阶段迁移，每阶段验证 Web API |
| 旧文件直接导入散落各处 | 中 | 高 | Phase 5.6 全局搜索所有 `goose_*` 导入引用并更新 |
| pyiec61850 API 版本差异 | 低 | 高 | `_IecApiAdapter` 封装兼容逻辑 |
| 持久化 DAO 切换影响启动流程 | 低 | 高 | `PersistenceAdapter` 支持 mock，启动流程端到端测试 |
| Capture 模块跨平台兼容 | 低 | 中 | 原始套接字逻辑不改动，仅迁移位置 |

---

## 9. 验收标准

- [ ] `plugins/goose/` 包含 6 个子模块 (types/publisher/subscriber/capture/manager/persistence)
- [ ] `GoosePlugin` 完整实现 `Iec61850Plugin` 协议
- [ ] `client.goose` 属性返回完整 `GoosePlugin` 实例
- [ ] `PluginRegistry.shutdown_all()` 正确停止所有 GOOSE 资源
- [ ] 旧文件 `goose_publisher.py` / `goose_subscriber.py` / `goose_capture.py` / `goose_manager.py` 已删除
- [ ] 全局搜索确认无任何文件引用旧导入路径
- [ ] `get_goose_manager()` 全局单例已删除
- [ ] 所有 Web API 端点 (`/api/channels/goose/`) 功能正常
- [ ] 无裸字符串常量 (`"init"`, `"connected"` 等 → `GooseState` 枚举)
- [ ] 无硬编码 MMS 常量 (`MMS_BOOLEAN = 0` 等 → `MmsType` 枚举)
- [ ] `GooseDataSetEntry` 使用 `frozen dataclass`
- [ ] 持久化逻辑通过 `PersistenceAdapter` 隔离，可 mock 测试
- [ ] 核心模块单元测试覆盖率 > 70%
