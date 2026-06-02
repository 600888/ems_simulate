# IEC 61850 统一模型架构重构计划

> 版本: 3.0  
> 日期: 2026-06-02  
> 替代文档:  
> - ~~iec61850-scl-file-module.md (v1.0)~~  
> - ~~iec61850-scl-refactoring-implementation.md (v2.0)~~  
> - ~~iec61850-model-export-optimization.md (v1.0)~~  
> 状态: 规划中

---

## 1. 核心问题：模型发现三重分裂

### 1.1 现状 — 三条独立的模型发现路径

当前系统中，IEC 61850 模型通过三条完全独立的路径被发现和表示，存在大量重复遍历：

```
路径 A — 连接时在线发现 (DataModelsPlugin.discover_model)
  IedConnection_getLogicalDeviceList          ┐
  IedConnection_getLogicalDeviceDirectory     │ 重复调用
  IedConnection_getLogicalNodeDirectory       │
  IedConnection_getDataDirectory              ┘
       ↓
  PointRegistry (address → ref/fc/iec_type)
  用途: 实时读写操作

路径 B — 导出时在线发现 (IEC61850ModelExporter.discover)
  IedConnection_getLogicalDeviceList          ┐
  IedConnection_getLogicalDeviceDirectory     │ 同样的 API
  IedConnection_getLogicalNodeDirectory       │ 再次完整遍历
  IedConnection_getDataDirectory              ┘
       ↓
  ServerModel (LDInfo → LNInfo → DOInfo → DAInfo)
  用途: JSON/CSV/XML/ICD/TreeText 导出

路径 C — 离线 ICD 解析 (IcdPointImporter / IcdGooseImporter)
  xml.etree.ElementTree 解析 .icd 文件
       ↓
  dict / list 散装数据
  用途: 从 ICD 文件导入测点和 GOOSE 配置
```

### 1.2 问题清单

| # | 问题 | 严重度 | 位置 |
|---|------|--------|------|
| 1 | **在线模型发现执行两次** | 🔴 严重 | `DataModelsPlugin` + `ModelExporter` 对同一 IED 调用相同的 pyiec61850 API，大型 IED 耗时可达数分钟 |
| 2 | **两套模型数据结构不互通** | 🔴 严重 | `PointRegistry` (扁平字典) vs `ServerModel` (嵌套树形)，无法互转或复用 |
| 3 | **ICD 解析逻辑分散** | 🔴 严重 | `IcdPointImporter`、`IcdGooseImporter` 各自独立解析 XML，无共享模型 |
| 4 | **无统一 SCL 对象模型** | 🔴 严重 | 缺少 `SclDocument` 等类型安全的数据类表示 |
| 5 | **大模型导出超时/OOM** | 🟡 中等 | `discover()` 同步阻塞 60s+ 超时，峰值内存达原始数据 10-15x |
| 6 | **前端循环引用崩溃** | 🟡 中等 | Vue 响应式系统 deep clone 触发循环引用 |
| 7 | **无进度反馈** | 🟡 中等 | 导出过程无进度、不可取消 |
| 8 | **临时文件泄漏** | 🟢 低 | `tempfile.mkdtemp` 未清理 |
| 9 | **递归深度无限制** | 🟢 低 | `_discover_sub_das()` 可能无限递归 |

### 1.3 根因分析

```
根因: 缺少统一的"模型表示层"

连接时需要的: address → ref 映射  ──┐
导出时需要的: 完整树形结构        ──┤── 都是从同一个 IED 在线遍历得来
ICD 导入需要的: 测点/GOOSE 配置   ──┘

但因为没有统一的中间表示，每个消费方都自己实现了一套发现逻辑。
```

**核心解法**: 引入 `IedModel` 作为统一的在线模型表示，一次发现、多处消费。

---

## 2. 目标架构

### 2.1 设计原则

| 原则 | 说明 | 应用 |
|------|------|------|
| **单一发现 (Discover Once)** | 在线模型只发现一次，所有消费方共享同一份 `IedModel` | `ModelDiscoveryService` |
| **单一职责 (SRP)** | 每个类/模块只有一个变更原因 | Parser 只解析，Validator 只校验，Exporter 只导出 |
| **开闭原则 (OCP)** | 对扩展开放，对修改关闭 | 新增 Exporter 无需修改 DiscoveryService |
| **依赖倒置 (DIP)** | 依赖抽象而非具体实现 | 消费方依赖 `IedModel` Protocol，不依赖发现实现 |
| **组合优于继承** | 优先使用组合和委托 | `IedModel` 组合 `LDModel`，而非继承 |
| **不可变优先** | 发现完成后模型应不可变 | `frozen=True` dataclass |

### 2.2 现代 Python 设计模式

| 模式 | Python 实现 | 应用位置 |
|------|-------------|----------|
| **Protocol (结构化子类型)** | `typing.Protocol` + `@runtime_checkable` | `ModelProvider`, `ModelExporter`, `SclParser` |
| **dataclass + slots + frozen** | `@dataclass(slots=True, frozen=True)` | 不可变模型 `IedModel`, `SclDocument` |
| **Builder** | 流式 API | `IedModelBuilder` 构建 `IedModel` |
| **Strategy** | 函数/类实现 Protocol | `exporter/` 中不同导出策略 |
| **Facade** | 编排类 | `ModelDiscoveryService`, `SclImportService` |
| **Registry** | 字典 + 工厂函数 | 校验规则注册、导出器注册 |
| **Result/Either** | `Success[T]` / `Failure[E]` | 发现和校验结果 |
| **Observer** | 回调函数 | 发现进度回调 |
| **Context Manager** | `with` 语句 | 文件操作、临时缓存 |
| **cached_property** | `functools.cached_property` | 派生属性延迟计算 |
| **Generator** | `yield` | 流式导出、惰性遍历 |

### 2.3 Python 版本要求

- **最低版本**: Python 3.10+（`match` 语句、`TypeAlias`、`ParamSpec`）
- **推荐版本**: Python 3.11+（`ExceptionGroup`、`TaskGroup`、性能优化）

---

## 3. 统一在线模型设计

### 3.1 核心数据模型 — `IedModel`

这是整个重构的关键。`IedModel` 是连接时在线发现和导出时消费的**唯一中间表示**。

```python
"""统一在线模型 — 一次发现，多处消费

IedModel 是 IED 在线模型的标准表示，替代当前:
- DataModelsPlugin 的 PointRegistry (扁平字典)
- IEC61850ModelExporter 的 ServerModel (嵌套 dataclass)

设计约束:
- 发现完成后不可变 (frozen=True)
- 自带序列化能力 (to_dict / to_flat_dict)
- 可派生 PointRegistry 和 ServerModel 的全部信息
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from functools import cached_property


@dataclass(slots=True, frozen=True)
class DARef:
    """数据属性引用 — 最细粒度的可寻址单元"""
    name: str = ""           # DA 名称 (如 "mag", "stVal", "ctlVal")
    path: str = ""           # 完整 DA 路径 (如 "mag.f", "cVal.mag.f")
    fc: str = ""             # 功能约束 (如 "MX", "ST", "CO")
    iec_type: str = ""       # IEC 类型 (如 "float", "boolean", "integer")
    sub_das: tuple[DARef, ...] = ()  # 结构体子属性 (BDA)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "fc": self.fc,
            "iecType": self.iec_type,
        }
        if self.sub_das:
            result["subDataAttributes"] = [bda.to_dict() for bda in self.sub_das]
        return result

    def to_flat_dict(self) -> dict[str, Any]:
        """扁平化表示 — 无嵌套，适合 CSV/表格"""
        return {
            "name": self.name,
            "path": self.path,
            "fc": self.fc,
            "iecType": self.iec_type,
        }

    @property
    def is_leaf(self) -> bool:
        """是否为叶子节点 (无 sub_das)"""
        return not self.sub_das

    def iter_leaves(self) -> Iterator[DARef]:
        """遍历所有叶子 DA (含 sub_das 展开)"""
        if self.is_leaf:
            yield self
        else:
            for bda in self.sub_das:
                yield from bda.iter_leaves()


@dataclass(slots=True, frozen=True)
class DORef:
    """数据对象引用"""
    name: str = ""           # DO 名称 (如 "TotW", "Ind1")
    ref: str = ""            # 完整 DO 引用 (如 "LD0/LLN0.TotW")
    cdc: str = ""            # 公共数据类 (如 "MV", "SPS", "SPC")
    frame_type: int = -1     # 0=遥测 1=遥信 2=遥控 3=遥调
    das: tuple[DARef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ref": self.ref,
            "cdc": self.cdc,
            "frameType": self.frame_type,
            "dataAttributes": [da.to_dict() for da in self.das],
        }

    @cached_property
    def primary_da(self) -> Optional[DARef]:
        """主值 DA — 用于读写操作的默认 DA"""
        from ...defs.da_patterns import DA_PATTERNS
        da_path = DA_PATTERNS.get(self.cdc, {}).get("da_path", "")
        for da in self.das:
            if da.path == da_path:
                return da
        return self.das[0] if self.das else None


@dataclass(slots=True, frozen=True)
class DataSetRef:
    """数据集引用"""
    name: str = ""
    ref: str = ""
    is_deletable: bool = False
    members: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ref": self.ref,
            "isDeletable": self.is_deletable,
            "members": list(self.members),
        }


@dataclass(slots=True, frozen=True)
class RCBRef:
    """报告控制块引用"""
    name: str = ""
    ref: str = ""
    rcb_type: str = ""       # "URCB" / "BRCB"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ref": self.ref, "type": self.rcb_type}


@dataclass(slots=True, frozen=True)
class GoCBRef:
    """GOOSE 控制块引用"""
    name: str = ""
    ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ref": self.ref}


@dataclass(slots=True, frozen=True)
class LNModel:
    """逻辑节点模型"""
    name: str = ""           # LN 实例名 (如 "MMXU1", "LLN0")
    ln_class: str = ""       # LN 类 (如 "MMXU", "LLN0")
    ref: str = ""            # 完整引用 (如 "LD0/MMXU1")
    dos: tuple[DORef, ...] = ()
    datasets: tuple[DataSetRef, ...] = ()
    rcb_list: tuple[RCBRef, ...] = ()
    gocb_list: tuple[GoCBRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "lnClass": self.ln_class,
            "ref": self.ref,
        }
        if self.dos:
            result["dataObjects"] = [do.to_dict() for do in self.dos]
        if self.datasets:
            result["dataSets"] = [ds.to_dict() for ds in self.datasets]
        if self.rcb_list:
            result["reportControlBlocks"] = [rcb.to_dict() for rcb in self.rcb_list]
        if self.gocb_list:
            result["gooseControlBlocks"] = [gocb.to_dict() for gocb in self.gocb_list]
        return result


@dataclass(slots=True, frozen=True)
class LDModel:
    """逻辑设备模型"""
    name: str = ""
    inst: str = ""
    lns: tuple[LNModel, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inst": self.inst,
            "logicalNodes": [ln.to_dict() for ln in self.lns],
        }


@dataclass(slots=True, frozen=True)
class IedModel:
    """IED 统一在线模型 — 一次发现，多处消费

    替代:
    - PointRegistry (连接时发现的扁平测点映射)
    - ServerModel (导出时发现的嵌套树形结构)

    特性:
    - frozen: 发现完成后不可变，线程安全
    - slots: 减少内存占用 40-50%
    - tuple: 子元素不可变，可哈希
    - cached_property: 派生属性延迟计算
    - to_dict: 自带序列化，无需外部转换函数
    """
    host: str = ""
    port: int = 102
    discover_time: str = ""
    lds: tuple[LDModel, ...] = ()

    # ===== 序列化 =====

    def to_dict(self) -> dict[str, Any]:
        """完整树形序列化"""
        return {
            "host": self.host,
            "port": self.port,
            "discover_time": self.discover_time,
            "logicalDevices": [ld.to_dict() for ld in self.lds],
            "summary": self.summary,
        }

    # ===== 统计摘要 =====

    @cached_property
    def summary(self) -> dict[str, int]:
        """模型统计 (延迟计算)"""
        return {
            "totalLDs": len(self.lds),
            "totalLNs": sum(len(ld.lns) for ld in self.lds),
            "totalDOs": sum(len(ln.dos) for ld in self.lds for ln in ld.lns),
            "totalDAs": sum(len(do.das) for ld in self.lds for ln in ld.lns for do in ln.dos),
            "totalDataSets": sum(len(ln.datasets) for ld in self.lds for ln in ld.lns),
            "totalRCBs": sum(len(ln.rcb_list) for ld in self.lds for ln in ld.lns),
            "totalGoCBs": sum(len(ln.gocb_list) for ld in self.lds for ln in ld.lns),
        }

    # ===== 派生: PointRegistry 所需数据 =====

    @cached_property
    def point_refs(self) -> dict[str, dict[str, Any]]:
        """生成 address → {ref, fc, iec_type, frame_type} 映射

        替代 DataModelsPlugin.discover_model() 的扁平测点列表，
        从 IedModel 直接派生，无需重新遍历 IED。
        """
        result: dict[str, dict[str, Any]] = {}
        for ld in self.lds:
            for ln in self.lns:
                for do in ln.dos:
                    primary = do.primary_da
                    if primary is None:
                        continue
                    address = f"{ld.name}/{ln.name}.{do.name}.{primary.path}"
                    result[address] = {
                        "ref": f"{do.ref}.{primary.path}",
                        "fc": primary.fc,
                        "iec_type": primary.iec_type,
                        "frame_type": do.frame_type,
                        "code": do.name,
                    }
        return result

    # ===== 遍历工具 =====

    def iter_dos(self) -> Iterator[tuple[LDModel, LNModel, DORef]]:
        """遍历所有 DO"""
        for ld in self.lds:
            for ln in ld.lns:
                for do in ln.dos:
                    yield ld, ln, do

    def iter_da_leaves(self) -> Iterator[tuple[LDModel, LNModel, DORef, DARef]]:
        """遍历所有叶子 DA (含 BDA 展开)"""
        for ld in self.lds:
            for ln in ld.lns:
                for do in ln.dos:
                    for da in do.das:
                        for leaf in da.iter_leaves():
                            yield ld, ln, do, leaf
```

### 3.2 模型发现服务 — `ModelDiscoveryService`

替代当前 `DataModelsPlugin.discover_model()` 和 `IEC61850ModelExporter.discover()` 两个独立实现。

```python
"""统一模型发现服务 — 一次发现，多处消费

核心变更:
- 连接时发现模型 → 构建 IedModel → 缓存
- 导出时直接使用缓存的 IedModel → 不再重新发现
- PointRegistry 从 IedModel 派生 → 不再独立发现
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, Protocol

from ...log import log
from ...defs import HAS_IEC61850, AcsiClass, FrameType
from ...defs.address import extract_ln_class, infer_fc_from_address, infer_iec_type_from_address
from ...defs.da_patterns import DA_PATTERNS, STRUCT_DA_EXPAND_ONLINE
from ...defs.ln_classes import (
    YC_LN_CLASSES, YX_LN_CLASSES, YK_LN_CLASSES, YT_LN_CLASSES,
)
from ...core.linked_list import get_list_from_linked_list

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class DiscoveryProgress(Protocol):
    """发现进度回调协议"""
    def __call__(self, phase: str, current: int, total: int, message: str) -> None: ...


class IedModelBuilder:
    """IedModel 构建器 — Builder 模式

    发现过程中使用可变内部状态，构建完成后产出不可变 IedModel。
    """

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._lds: list[_LDBuilder] = []

    def add_ld(self, name: str, inst: str) -> _LDBuilder:
        ld = _LDBuilder(name=name, inst=inst)
        self._lds.append(ld)
        return ld

    def build(self) -> IedModel:
        """构建不可变 IedModel"""
        return IedModel(
            host=self._host,
            port=self._port,
            discover_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            lds=tuple(ld.build() for ld in self._lds),
        )


class _LDBuilder:
    __slots__ = ("name", "inst", "_lns")
    def __init__(self, name: str, inst: str):
        self.name = name
        self.inst = inst
        self._lns: list[_LNBuilder] = []

    def add_ln(self, name: str, ln_class: str, ref: str) -> _LNBuilder:
        ln = _LNBuilder(name=name, ln_class=ln_class, ref=ref)
        self._lns.append(ln)
        return ln

    def build(self) -> LDModel:
        return LDModel(
            name=self.name, inst=self.inst,
            lns=tuple(ln.build() for ln in self._lns),
        )


class _LNBuilder:
    __slots__ = ("name", "ln_class", "ref", "_dos", "_datasets", "_rcbs", "_gocbs")
    def __init__(self, name: str, ln_class: str, ref: str):
        self.name = name
        self.ln_class = ln_class
        self.ref = ref
        self._dos: list[DORef] = []
        self._datasets: list[DataSetRef] = []
        self._rcbs: list[RCBRef] = []
        self._gocbs: list[GoCBRef] = []

    def add_do(self, do: DORef) -> None:
        self._dos.append(do)

    def add_dataset(self, ds: DataSetRef) -> None:
        self._datasets.append(ds)

    def add_rcb(self, rcb: RCBRef) -> None:
        self._rcbs.append(rcb)

    def add_gocb(self, gocb: GoCBRef) -> None:
        self._gocbs.append(gocb)

    def build(self) -> LNModel:
        return LNModel(
            name=self.name, ln_class=self.ln_class, ref=self.ref,
            dos=tuple(self._dos),
            datasets=tuple(self._datasets),
            rcb_list=tuple(self._rcbs),
            gocb_list=tuple(self._gocbs),
        )


class ModelDiscoveryService:
    """统一模型发现服务

    替代:
    - DataModelsPlugin.discover_model() (连接时发现)
    - IEC61850ModelExporter.discover() (导出时发现)

    生命周期:
    1. connect() 时调用 discover() → 缓存 IedModel
    2. 读操作 → 从 IedModel 派生 PointRegistry
    3. 导出操作 → 直接使用缓存的 IedModel
    """

    def __init__(self):
        self._model: Optional[IedModel] = None
        self._model_timestamp: float = 0.0

    @property
    def model(self) -> Optional[IedModel]:
        """获取当前缓存的 IedModel"""
        return self._model

    @property
    def is_discovered(self) -> bool:
        return self._model is not None

    def invalidate(self) -> None:
        """使缓存失效 (断开连接时调用)"""
        self._model = None
        self._model_timestamp = 0.0

    def discover(
        self,
        connection: Any,
        *,
        on_error: str = "skip",
        max_depth: int = 10,
        progress: Optional[DiscoveryProgress] = None,
    ) -> IedModel:
        """在线发现 IED 完整数据模型

        遍历 LD → LN → DO/DS/RCB/GoCB → DA/BDA，构建不可变 IedModel。

        Args:
            connection: IedConnection 实例
            on_error: 节点失败策略 ("skip" | "abort")
            max_depth: 递归发现子 DA 的最大深度
            progress: 进度回调

        Returns:
            IedModel 不可变模型对象
        """
        if self._model is not None:
            return self._model

        log.info("开始 IEC 61850 统一模型发现...")
        start_time = time.time()

        conn = connection.connection if hasattr(connection, 'connection') else connection

        # 获取 LD 列表
        with self._error_guard("获取逻辑设备列表", on_error):
            ld_names = self._browse_logical_devices(conn)

        if not ld_names:
            log.warning("未发现任何逻辑设备")
            self._model = IedModel()
            return self._model

        builder = IedModelBuilder(
            host=getattr(connection, 'ip', ''),
            port=getattr(connection, 'port', 102),
        )

        total_lds = len(ld_names)
        for i, ld_name in enumerate(ld_names):
            progress and progress("discovering", i, total_lds, f"发现 LD: {ld_name}")
            with self._error_guard(f"LD {ld_name}", on_error):
                self._discover_ld(conn, builder, ld_name, max_depth=max_depth, on_error=on_error)

        self._model = builder.build()
        self._model_timestamp = time.time()

        elapsed = time.time() - start_time
        log.info(
            f"统一模型发现完成, 耗时 {elapsed:.2f}s, "
            f"{self._model.summary}"
        )
        return self._model

    def _discover_ld(self, conn, builder: IedModelBuilder,
                     ld_name: str, *, max_depth: int, on_error: str) -> None:
        """发现单个 LD 的完整模型"""
        ld_builder = builder.add_ld(ld_name, ld_name)

        with self._error_guard(f"LN 列表 {ld_name}", on_error):
            ln_names = self._browse_logical_nodes(conn, ld_name)

        for ln_name in ln_names:
            ln_ref = f"{ld_name}/{ln_name}"
            ln_class = extract_ln_class(ln_name) or ""
            ln_builder = ld_builder.add_ln(ln_name, ln_class, ln_ref)

            with self._error_guard(f"LN {ln_ref}", on_error):
                # DO + DA
                for do in self._discover_data_objects(conn, ln_ref, ln_name, max_depth):
                    ln_builder.add_do(do)
                # DataSet
                for ds in self._discover_datasets(conn, ld_name, ln_ref):
                    ln_builder.add_dataset(ds)
                # RCB
                for rcb in self._discover_rcbs(conn, ln_ref):
                    ln_builder.add_rcb(rcb)
                # GoCB
                for gocb in self._discover_gocbs(conn, ln_ref):
                    ln_builder.add_gocb(gocb)

    @contextmanager
    def _error_guard(self, ref: str, on_error: str = "skip"):
        """节点发现错误守卫 — Context Manager 模式"""
        try:
            yield
        except Exception as e:
            log.warning(f"发现 {ref} 时出错: {e}")
            if on_error == "abort":
                raise

    # ===== 底层 pyiec61850 调用 (唯一调用点) =====

    def _browse_logical_devices(self, conn) -> list[str]:
        result = iec61850.IedConnection_getLogicalDeviceList(conn)
        ld_list = result[0] if isinstance(result, (list, tuple)) else result
        return get_list_from_linked_list(ld_list)

    def _browse_logical_nodes(self, conn, ld_name: str) -> list[str]:
        result = iec61850.IedConnection_getLogicalDeviceDirectory(conn, ld_name)
        ln_list = result[0] if isinstance(result, (list, tuple)) else result
        return get_list_from_linked_list(ln_list)

    def _discover_data_objects(self, conn, ln_ref: str, ln_name: str,
                               max_depth: int) -> list[DORef]:
        """发现 LN 下所有 DO 及其 DA/BDA"""
        do_refs = []

        result = iec61850.IedConnection_getLogicalNodeDirectory(
            conn, ln_ref, AcsiClass.DATA_OBJECT
        )
        do_list = result[0] if isinstance(result, (list, tuple)) else result
        do_names = get_list_from_linked_list(do_list)

        for do_name in do_names:
            do_ref = f"{ln_ref}.{do_name}"
            # 推断 CDC 和 frame_type
            cdc, frame_type = self._infer_cdc_and_frame_type(do_name, ln_name)

            # 发现 DA
            das = self._discover_data_attributes(conn, do_ref, max_depth=max_depth)

            do_refs.append(DORef(
                name=do_name,
                ref=do_ref,
                cdc=cdc,
                frame_type=frame_type,
                das=tuple(das),
            ))

        return do_refs

    def _discover_data_attributes(self, conn, do_ref: str,
                                   max_depth: int = 10) -> list[DARef]:
        """发现 DO 下所有 DA"""
        da_refs = []

        result = iec61850.IedConnection_getDataDirectory(conn, do_ref)
        da_list = result[0] if isinstance(result, (list, tuple)) else result
        da_names = get_list_from_linked_list(da_list)

        for da_name in da_names:
            da_full_ref = f"{do_ref}.{da_name}"
            fc = infer_fc_from_address(da_full_ref)
            iec_type = infer_iec_type_from_address(da_full_ref)

            # 递归发现 BDA (结构体 DA)
            sub_das = ()
            if STRUCT_DA_EXPAND_ONLINE.get(da_name) and max_depth > 0:
                sub_das = tuple(
                    self._discover_sub_das(conn, da_full_ref, fc,
                                           depth=1, max_depth=max_depth)
                )

            da_refs.append(DARef(
                name=da_name,
                path=da_name,
                fc=fc,
                iec_type=iec_type,
                sub_das=sub_das,
            ))

        return da_refs

    def _discover_sub_das(self, conn, parent_ref: str, parent_fc: str,
                          *, depth: int = 0, max_depth: int = 10) -> list[DARef]:
        """递归发现子 DA — 带深度限制"""
        if depth >= max_depth:
            log.warning(f"递归深度达到上限 {max_depth}, 停止展开: {parent_ref}")
            return []

        result = iec61850.IedConnection_getDataDirectory(conn, parent_ref)
        da_list = result[0] if isinstance(result, (list, tuple)) else result
        da_names = get_list_from_linked_list(da_list)

        sub_das = []
        for da_name in da_names:
            da_full_ref = f"{parent_ref}.{da_name}"
            fc = infer_fc_from_address(da_full_ref)
            iec_type = infer_iec_type_from_address(da_full_ref)

            nested = self._discover_sub_das(
                conn, da_full_ref, fc, depth=depth + 1, max_depth=max_depth
            )

            sub_das.append(DARef(
                name=da_name,
                path=f"{parent_ref.split('.')[-1]}.{da_name}" if depth > 0 else da_name,
                fc=fc,
                iec_type=iec_type,
                sub_das=tuple(nested),
            ))

        return sub_das

    def _infer_cdc_and_frame_type(self, do_name: str, ln_name: str) -> tuple[str, int]:
        """推断 DO 的 CDC 和 frame_type"""
        from ...defs.ln_classes import SIGNAL_DOS
        ln_class = extract_ln_class(ln_name) or ""

        # 简单地址模式: DO 名带前缀
        if do_name.startswith("MV_"):
            return "MV", 0
        elif do_name.startswith("SPS_"):
            return "SPS", 1
        elif do_name.startswith("SPC_"):
            return "SPC", 2
        elif do_name.startswith("APC_"):
            return "APC", 3

        # 动态模型模式: 根据 LN class 推断
        if ln_class in YC_LN_CLASSES:
            return "", 0
        elif ln_class in YX_LN_CLASSES:
            return "", 1
        elif ln_class in YK_LN_CLASSES:
            return "", 2
        elif ln_class in YT_LN_CLASSES:
            return "", 3

        return "", -1

    def _discover_datasets(self, conn, ld_name: str, ln_ref: str) -> list[DataSetRef]:
        """发现 LN 下所有 DataSet"""
        datasets = []
        result = iec61850.IedConnection_getLogicalNodeDirectory(
            conn, ln_ref, AcsiClass.DATA_SET
        )
        ds_list = result[0] if isinstance(result, (list, tuple)) else result
        ds_names = get_list_from_linked_list(ds_list)

        for ds_name in ds_names:
            ds_ref = f"{ln_ref}.{ds_name}"
            is_deletable = iec61850.IedConnection_isDataSetEditable(
                conn, ds_ref
            ) if hasattr(iec61850, 'IedConnection_isDataSetEditable') else False

            members = self._discover_dataset_members(conn, ds_ref)
            datasets.append(DataSetRef(
                name=ds_name, ref=ds_ref,
                is_deletable=is_deletable,
                members=tuple(members),
            ))

        return datasets

    def _discover_dataset_members(self, conn, ds_ref: str) -> list[dict[str, str]]:
        """发现 DataSet 成员"""
        members = []
        result = iec61850.IedConnection_getDataSetValues(conn, ds_ref)
        # ... 解析成员
        return members

    def _discover_rcbs(self, conn, ln_ref: str) -> list[RCBRef]:
        """发现 LN 下所有 RCB"""
        rcbs = []
        for acsi_val in [AcsiClass.URCB, AcsiClass.BRCB]:
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                conn, ln_ref, acsi_val
            )
            rcb_list = result[0] if isinstance(result, (list, tuple)) else result
            rcb_names = get_list_from_linked_list(rcb_list)

            rcb_type = "URCB" if acsi_val == AcsiClass.URCB else "BRCB"
            for rcb_name in rcb_names:
                rcbs.append(RCBRef(
                    name=rcb_name,
                    ref=f"{ln_ref}.{rcb_name}",
                    rcb_type=rcb_type,
                ))
        return rcbs

    def _discover_gocbs(self, conn, ln_ref: str) -> list[GoCBRef]:
        """发现 LN 下所有 GoCB"""
        gocbs = []
        result = iec61850.IedConnection_getLogicalNodeDirectory(
            conn, ln_ref, AcsiClass.GOOSE_CONTROL_BLOCK
        )
        gocb_list = result[0] if isinstance(result, (list, tuple)) else result
        gocb_names = get_list_from_linked_list(gocb_list)

        for gocb_name in gocb_names:
            gocbs.append(GoCBRef(
                name=gocb_name,
                ref=f"{ln_ref}.{gocb_name}",
            ))
        return gocbs
```

### 3.3 PointRegistry 从 IedModel 派生

```python
"""PointRegistry 衍生逻辑 — 从 IedModel 派生，不再独立发现"""
from __future__ import annotations

from typing import Optional


def build_registry_from_model(model: IedModel, registry: "PointRegistry") -> list[dict[str, Any]]:
    """从 IedModel 构建 PointRegistry — 替代 DataModelsPlugin.discover_model()

    Args:
        model: 已发现的 IedModel
        registry: 待填充的 PointRegistry

    Returns:
        发现的测点列表 (向后兼容)
    """
    discovered_points: list[dict[str, Any]] = []

    for address, info in model.point_refs.items():
        registry.set_ref(address, info["ref"])
        registry.set_fc(address, info["fc"])
        registry.set_iec_type(address, info["iec_type"])

        discovered_points.append({
            "address": address,
            "frame_type": info["frame_type"],
            "ref": info["ref"],
            "code": info["code"],
            "fc": info["fc"],
            "iec_type": info["iec_type"],
        })

    return discovered_points
```

### 3.4 导出器直接消费 IedModel

```python
"""模型导出器 — 直接消费 IedModel，不再重新发现"""
from __future__ import annotations

from typing import Any, Optional, Protocol, Iterator


class ModelExporter(Protocol):
    """导出器协议 — Strategy 模式"""
    def export(self, model: IedModel, output_path: str, **kwargs) -> str: ...
    def export_streaming(self, model: IedModel, **kwargs) -> Iterator[str]: ...


class JsonExporter:
    """JSON 导出器"""

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        """导出完整 JSON 文件"""
        import json
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(model.to_dict(), f, ensure_ascii=False, indent=2)
        return output_path

    def export_streaming(self, model: IedModel, **kwargs) -> Iterator[str]:
        """流式生成 JSON — 内存 O(1)"""
        yield '{"host":"' + model.host + '",'
        yield '"port":' + str(model.port) + ','
        yield '"discover_time":"' + model.discover_time + '",'
        yield '"logicalDevices":['

        first_ld = True
        for ld in model.lds:
            if not first_ld:
                yield ','
            first_ld = False
            yield json.dumps(ld.to_dict(), ensure_ascii=False)

        yield ']}'


class CsvExporter:
    """CSV 导出器 — 增量逐行写入"""

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        import csv
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["LD", "LN", "LN类", "DO", "DA路径", "FC", "数据类型", "帧类型", "完整引用"])

            for ld, ln, do, da in model.iter_da_leaves():
                writer.writerow([
                    ld.name, ln.name, ln.ln_class,
                    do.name, da.path, da.fc,
                    da.iec_type, str(do.frame_type),
                    f"{do.ref}.{da.path}",
                ])

        return output_path


class IcdExporter:
    """ICD/SCL 导出器"""

    def export(self, model: IedModel, output_path: str, *,
               ied_name: str = "", **kwargs) -> str:
        """导出 ICD 文件 (使用 xmltodict，后续可升级为 lxml 流式)"""
        import xmltodict
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        scl_dict = self._model_to_scl_dict(model, ied_name=ied_name)
        xml_str = xmltodict.unparse(scl_dict, pretty=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)

        return output_path

    def _model_to_scl_dict(self, model: IedModel, *, ied_name: str) -> dict:
        """IedModel → SCL XML dict"""
        # ... 实现 (从现有 _model_to_scl_dict 迁移)
        ...


class TreeTextExporter:
    """树形文本导出器"""

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        lines = []
        lines.append(f"IED Model: {model.host}:{model.port}")
        lines.append(f"Discovered: {model.discover_time}")
        lines.append("")

        for ld in model.lds:
            lines.append(f"├── {ld.name}")
            for ln in ld.lns:
                lines.append(f"│   ├── {ln.name} [{ln.ln_class}]")
                for do in ln.dos:
                    lines.append(f"│   │   ├── {do.name} (FT={do.frame_type})")
                    for da in do.das:
                        lines.append(f"│   │   │   ├── {da.name} [{da.fc}] {da.iec_type}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path


# 导出器注册表
EXPORTERS: dict[str, type[ModelExporter]] = {
    "json": JsonExporter,
    "csv": CsvExporter,
    "icd": IcdExporter,
    "xml": IcdExporter,      # XML 和 ICD 使用相同导出器
    "tree": TreeTextExporter,
}
```

---

## 4. SCL 离线解析模块设计

### 4.1 SCL 对象模型 (`plugins/scl/model/`)

在线模型 (`IedModel`) 与离线模型 (`SclDocument`) 是两个独立的数据层次：

```
在线模型 (IedModel)          离线模型 (SclDocument)
  来自: 在线连接发现            来自: ICD/SCD/CID 文件解析
  特点: 动态、实时              特点: 静态、完整
  包含: 运行时可访问的测点       包含: 全部类型定义 + 通信配置
  缺少: 类型定义层级            缺少: 运行时实际值

  可以互相转换:
  IedModel + SclDocument → 完整的 IED 描述
```

核心模型类定义（使用 `@dataclass(slots=True)` 优化内存）：

| 文件 | 核心类 | 说明 |
|------|--------|------|
| `model/scl_base.py` | `SclElement` | SCL 元素基类 |
| `model/scl_document.py` | `SclDocument`, `SclDataTypeTemplates` | SCL 文档顶层容器 |
| `model/ied.py` | `SclIED`, `SclAccessPoint`, `SclServer` | IED 模型 |
| `model/logical_device.py` | `SclLogicalDevice`, `SclLN0`, `SclLN` | 逻辑设备/节点 |
| `model/data_type.py` | `SclLNodeType`, `SclDOType`, `SclDAType`, `SclEnumType` | 数据类型模板 |
| `model/dataset.py` | `SclDataSet`, `SclFCDA` | 数据集 |
| `model/control_block.py` | `SclGSEControl`, `SclReportControl`, `SclSVControl` | 控制块 |
| `model/communication.py` | `SclCommunication`, `SclSubNetwork`, `SclConnectedAP` | 通信配置 |
| `model/enums.py` | `FunctionalConstraint`, `CommonDataClass`, `PointCategory` | 枚举常量 |

> 详细的 dataclass 定义见原文档 v2.0 §2，此处不再重复。

### 4.2 解析引擎 (`plugins/scl/parser/`)

| 文件 | 核心类 | Protocol |
|------|--------|----------|
| `parser/protocols.py` | `SclParserProtocol` | `parse_file()` / `parse_string()` |
| `parser/scl_parser.py` | `SclParser` | 统一解析 ICD/SCD/CID |
| `parser/namespace.py` | `NamespaceHelper` | 命名空间检测 |
| `parser/type_resolver.py` | `TypeResolver` | 类型引用解析 |

### 4.3 校验引擎 (`plugins/scl/validator/`)

| 文件 | 核心类 | Protocol |
|------|--------|----------|
| `validator/result.py` | `ValidationResult`, `ValidationIssue`, `Severity` | Result 模式 |
| `validator/rules.py` | `ValidationRule`, `ValidationRuleRegistry` | Strategy + Registry |
| `validator/builtin_rules.py` | `IedExistenceRule`, `TypeReferenceIntegrityRule` 等 | 内置规则 |

### 4.4 转换器 (`plugins/scl/transformer/`)

| 文件 | 核心类 | 输入 → 输出 |
|------|--------|-------------|
| `transformer/point_transformer.py` | `SclPointTransformer` | `SclDocument → PointTransformResult` |
| `transformer/goose_transformer.py` | `SclGooseTransformer` | `SclDocument → GooseTransformResult` |
| `transformer/report_transformer.py` | `SclReportTransformer` | `SclDocument → ReportTransformResult` |
| `transformer/server_model_builder.py` | `SclServerModelBuilder` | `SclDocument → IedModel` |

### 4.5 服务层 (`plugins/scl/service/`)

| 文件 | 核心类 | 模式 |
|------|--------|------|
| `service/container.py` | `SclServiceContainer` | DI 容器 (dataclass + 默认参数) |
| `service/file_manager.py` | `SclFileManager` | 文件管理 (Context Manager) |
| `service/import_service.py` | `SclImportService` | Facade (解析→校验→转换→持久化) |
| `service/diff_service.py` | `SclDiffService` | 文件对比 |

---

## 5. 集成方案：统一模型发现 + SCL 离线解析

### 5.1 调用链变更

**当前 (三次发现)**:
```
连接时: DataModelsPlugin.discover_model() → PointRegistry
导出时: ModelExporterPlugin.discover_server_model() → ServerModel (重新遍历)
ICD导入: IcdPointImporter.import_from_icd() → 散装 dict
```

**目标 (一次发现 + 离线解析)**:
```
连接时: ModelDiscoveryService.discover() → IedModel (缓存)
  ├→ PointRegistry (从 IedModel 派生，不再遍历)
  ├→ 导出器 (直接消费 IedModel，不再遍历)
  └→ GOOSE/Report 插件 (从 IedModel 获取控制块信息)

ICD导入: SclParser.parse_file() → SclDocument
  ├→ SclPointTransformer → 测点数据
  ├→ SclGooseTransformer → GOOSE 配置
  └→ SclReportTransformer → Report 配置
```

### 5.2 IEC61850Client 变更

```python
class IEC61850Client:
    """变更点摘要"""

    def __init__(self, ...):
        # 新增: 统一发现服务
        self._discovery = ModelDiscoveryService()

    def connect(self, ...):
        # ... 建立连接 ...
        # 统一发现: 一次遍历，构建 IedModel
        self._discovery.discover(self._connection)
        # 从 IedModel 派生 PointRegistry
        build_registry_from_model(self._discovery.model, self._registry)

    @property
    def model(self) -> Optional[IedModel]:
        """获取缓存的 IedModel"""
        return self._discovery.model

    def disconnect(self):
        self._discovery.invalidate()
        # ...

    # 导出: 不再重新发现
    def export_model(self, export_type: str, **kwargs) -> str:
        model = self._discovery.model
        if model is None:
            raise RuntimeError("模型未发现，请先连接设备")
        exporter_cls = EXPORTERS.get(export_type)
        if exporter_cls is None:
            raise ValueError(f"不支持的导出类型: {export_type}")
        exporter = exporter_cls()
        return exporter.export(model, **kwargs)
```

### 5.3 DataModelsPlugin 变更

```python
class DataModelsPlugin:
    """变更: discover_model() 不再独立遍历，改为从 IedModel 派生"""

    def discover_model(self) -> list[dict[str, Any]]:
        if not self._client or not self._client.model:
            return []
        # 从已缓存的 IedModel 派生 PointRegistry
        return build_registry_from_model(self._client.model, self._registry)
```

### 5.4 ModelExporterPlugin 变更

```python
class ModelExporterPlugin:
    """变更: 不再重新发现，直接使用 IedModel"""

    def discover_server_model(self, **kwargs) -> IedModel:
        """直接返回缓存的 IedModel"""
        if not self._client or not self._client.model:
            raise RuntimeError("模型未发现")
        return self._client.model
```

---

## 6. 导出优化设计

### 6.1 流式 JSON 导出

```python
class JsonStreamWriter:
    """流式 JSON 写入器 — 零中间 dict 分配

    __slots__ 优化内存，链式调用优化可读性。
    """
    __slots__ = ('_writer', '_first', '_stack')

    def __init__(self, writer: Callable[[str], None]):
        self._writer = writer
        self._first = True
        self._stack = []

    def object_start(self) -> JsonStreamWriter:
        self._write('{')
        self._first = True
        self._stack.append(True)
        return self

    def object_end(self) -> JsonStreamWriter:
        self._stack.pop()
        self._write('}')
        self._first = not self._stack[-1] if self._stack else True
        return self

    def key(self, name: str) -> JsonStreamWriter:
        if not self._first:
            self._write(',')
        self._write(f'"{name}":')
        self._first = True
        return self

    def value(self, val: Any) -> JsonStreamWriter:
        if not self._first:
            self._write(',')
        self._write(json.dumps(val, ensure_ascii=False))
        self._first = False
        return self

    def _write(self, chunk: str) -> None:
        self._writer(chunk)
```

### 6.2 异步导出 + 进度反馈

```python
@dataclass
class ExportTask:
    """异步导出任务"""
    task_id: str
    device_name: str
    export_type: str
    status: Literal["pending", "exporting", "done", "failed"]
    progress: float = 0.0
    result_path: str = ""
    error: str = ""


@device_router.post("/export-model")
async def export_model(req: ExportModelRequest, request: Request):
    """导出 IEC 61850 模型 — 使用缓存的 IedModel，无需重新发现"""
    device = _get_device(req.device_name, request)
    client = device.client

    # 获取缓存的 IedModel
    model = client.model
    if model is None:
        return BaseResponse(code=400, message="模型未发现，请先连接设备")

    # 小模型: 直接流式返回
    # 大模型: 异步任务
    ...
```

### 6.3 临时文件清理

```python
import atexit
import shutil
from pathlib import Path
from starlette.background import BackgroundTask

_temp_dirs: list[str] = []

def _cleanup_temp_dirs() -> None:
    for d in _temp_dirs:
        shutil.rmtree(d, ignore_errors=True)

atexit.register(_cleanup_temp_dirs)


async def export_model(req, request):
    tmp_dir = tempfile.mkdtemp(prefix="ems_export_")
    _temp_dirs.append(tmp_dir)

    try:
        # ... 导出逻辑 ...
        response = FileResponse(path=tmp_path, filename=filename)
        response.background = BackgroundTask(
            lambda: shutil.rmtree(tmp_dir, ignore_errors=True)
        )
        return response
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
```

### 6.4 前端循环引用修复

```typescript
// deviceApi.ts — 文件下载绕过响应式深拷贝
export async function exportModel(deviceName: string, exportType: string): Promise<void> {
    const baseURL = import.meta.env.VUE_APP_API_BASE || '/';
    const response = await fetch(`${baseURL}/api/devices/export-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_name: deviceName, export_type: exportType }),
        cache: 'no-store',  // 关键: 不缓存大响应
    });

    if (!response.ok) throw new Error(`导出失败 (HTTP ${response.status})`);

    const blob = await response.blob();
    // 使用 File System Access API 保存
    const handle = await (window as any).showSaveFilePicker({
        suggestedName: `${deviceName}_model.${extMap[exportType]}`,
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
}
```

---

## 7. 完整模块依赖关系

```
src/proto/iec61850/
│
├── defs/                          ← 公共定义，无外部依赖
│   ├── constants.py               (FC, IEC_TYPE, AcsiClass, FrameType)
│   ├── address.py                 (parse_ref, infer_fc, infer_iec_type)
│   ├── da_patterns.py             (DA_PATTERNS, EXTRA_DA_INFO, ...)
│   ├── ln_classes.py              (YC/YX/YK/YT_LN_CLASSES)
│   └── types.py                   (IecType, FrameType, AcsiClass)
│
├── core/                          ← 核心连接与读写，依赖 defs/
│   ├── connection.py              (IedConnection 生命周期)
│   ├── mms_value.py               (MmsValue ↔ Python)
│   ├── linked_list.py             (C LinkedList → Python list)
│   ├── reader.py                  (数据读取)
│   ├── writer.py                  (数据写入)
│   ├── reconnect.py               (指数退避重连)
│   └── registry.py                (PointRegistry)
│
├── model/                         ← 统一在线模型，无外部依赖 ★新增
│   ├── __init__.py
│   ├── ied_model.py               (IedModel, LDModel, LNModel, DORef, DARef, ...)
│   ├── discovery.py               (ModelDiscoveryService, IedModelBuilder)
│   └── registry_bridge.py         (build_registry_from_model)
│
├── plugins/
│   ├── __init__.py                (PluginRegistry)
│   ├── base.py                    (Iec61850Plugin Protocol)
│   │
│   ├── datamodels/                ← 简化: 从 IedModel 派生，不再独立发现
│   │   └── __init__.py            (DataModelsPlugin — 薄封装)
│   │
│   ├── model_exporter/            ← 简化: 直接消费 IedModel，不再独立发现
│   │   ├── __init__.py            (ModelExporterPlugin)
│   │   ├── exporters/             ★新增: Strategy 模式导出器
│   │   │   ├── __init__.py
│   │   │   ├── json.py            (JsonExporter)
│   │   │   ├── csv.py             (CsvExporter)
│   │   │   ├── icd.py             (IcdExporter)
│   │   │   └── tree.py            (TreeTextExporter)
│   │   └── stream_writer.py       (JsonStreamWriter)
│   │
│   ├── scl/                       ← 离线 SCL 解析，纯 Python ★新增
│   │   ├── model/                 (SclDocument, SclIED, SclLNodeType, ...)
│   │   ├── parser/                (SclParser, NamespaceHelper, TypeResolver)
│   │   ├── validator/             (ValidationRuleRegistry, builtin_rules)
│   │   ├── transformer/           (SclPointTransformer, SclGooseTransformer, ...)
│   │   └── service/               (SclImportService, SclFileManager)
│   │
│   ├── datasets/                  (DataSet 操作)
│   ├── goose/                     (GOOSE 发布/订阅)
│   ├── reports/                   (报告控制块)
│   ├── files/                     (远程文件操作)
│   ├── log_plugin/                (日志)
│   ├── setting_groups/            (设定组)
│   └── sv/                        (采样值)
│
├── iec61850_client.py             ← Facade: 持有 ModelDiscoveryService
├── iec61850_server.py
└── log.py
```

**依赖规则:**
- `defs/` → 无外部依赖
- `model/` → 无外部依赖 (纯 dataclass)
- `core/` → 依赖 `defs/`
- `plugins/` → 依赖 `defs/` + `core/` + `model/`
- `plugins/scl/` → 不依赖 `pyiec61850`、FastAPI、SQLAlchemy
- `iec61850_client.py` → 依赖所有子模块

---

## 8. 分阶段实施计划

### Phase 1: 统一在线模型 (3 天) [P0 🔴]

**目标**: 消除模型发现重复，一次发现多处消费

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 1.1 | 创建 `model/` 子包 | `model/__init__.py`, `model/ied_model.py` | `IedModel` 可实例化 |
| 1.2 | 实现 `IedModel` 全部 dataclass | `model/ied_model.py` | `frozen=True, slots=True`, `to_dict()` 正常 |
| 1.3 | 实现 `ModelDiscoveryService` | `model/discovery.py` | 统一 `discover()` 替代两处独立发现 |
| 1.4 | 实现 `IedModelBuilder` | `model/discovery.py` | Builder 模式构建不可变模型 |
| 1.5 | 实现 `build_registry_from_model()` | `model/registry_bridge.py` | 从 `IedModel` 派生 `PointRegistry` |
| 1.6 | 修改 `IEC61850Client` | `iec61850_client.py` | `connect()` 使用 `ModelDiscoveryService` |
| 1.7 | 修改 `DataModelsPlugin` | `plugins/datamodels/__init__.py` | `discover_model()` 改为从 `IedModel` 派生 |
| 1.8 | 修改 `ModelExporterPlugin` | `plugins/model_exporter/__init__.py` | 使用缓存的 `IedModel` 而非重新发现 |
| 1.9 | 对比验证 | 手动测试 | 连接+导出结果与修改前一致 |

**关键约束:**
- `model/` 不依赖 `pyiec61850`、FastAPI、SQLAlchemy
- `IedModel` 使用 `frozen=True` 保证线程安全
- `ModelDiscoveryService` 是调用 `pyiec61850` API 的**唯一入口**

### Phase 2: 导出器拆分与优化 (2 天) [P0 🔴]

**目标**: 导出器直接消费 `IedModel`，支持流式导出

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 2.1 | 拆分 `JsonExporter` | `plugins/model_exporter/exporters/json.py` | 导出 JSON 与原实现一致 |
| 2.2 | 拆分 `CsvExporter` | `plugins/model_exporter/exporters/csv.py` | 导出 CSV 与原实现一致 |
| 2.3 | 拆分 `IcdExporter` | `plugins/model_exporter/exporters/icd.py` | 导出 ICD 与原实现一致 |
| 2.4 | 拆分 `TreeTextExporter` | `plugins/model_exporter/exporters/tree.py` | 导出 TreeText 与原实现一致 |
| 2.5 | 实现 `JsonStreamWriter` | `plugins/model_exporter/stream_writer.py` | 流式 JSON 写入 |
| 2.6 | 实现导出器注册表 | `plugins/model_exporter/exporters/__init__.py` | Strategy 模式选择导出器 |
| 2.7 | 临时文件清理 | `router.py` | `BackgroundTask` 清理 |

### Phase 3: 前端修复 (0.5 天) [P0 🔴]

**目标**: 消除循环引用崩溃

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 3.1 | 确认 fetch 通道独立 | `deviceApi.ts` | `exportModel()` 不经 axios 拦截器 |
| 3.2 | 添加 `cache: 'no-store'` | `deviceApi.ts` | 大响应不缓存 |

### Phase 4: SCL 对象模型与解析引擎 (3 天) [P1 🟡]

**目标**: 建立离线 SCL 解析基础设施

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 4.1 | 创建 `scl/` 模块结构 | `plugins/scl/` | 子包可导入 |
| 4.2 | 实现 `model/enums.py` | 枚举常量 | `CDC_CATEGORY_MAP` 覆盖所有 CDC |
| 4.3 | 实现 `model/` 全部模型类 | `plugins/scl/model/*.py` | 所有 dataclass 定义完成 |
| 4.4 | 实现 `SclParser` | `plugins/scl/parser/scl_parser.py` | 解析 KG_BAMS.icd 成功 |
| 4.5 | 实现 `NamespaceHelper` | `plugins/scl/parser/namespace.py` | 有/无命名空间均可处理 |
| 4.6 | 实现 `TypeResolver` | `plugins/scl/parser/type_resolver.py` | 类型引用可解析 |
| 4.7 | 单元测试 | `tests/` | 解析结果与现有 Importer 一致 |

### Phase 5: 校验引擎与模型转换器 (3 天) [P1 🟡]

**目标**: 替代分散的 ICD 导入逻辑

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 5.1 | 实现 `validator/result.py` | `ValidationResult` 可合并 |
| 5.2 | 实现 `validator/rules.py` | Protocol + Registry 可用 |
| 5.3 | 实现内置校验规则 | 4 个规则 | 可检测引用缺失等错误 |
| 5.4 | 实现 `SclPointTransformer` | 输出与 `IcdPointImporter` 一致 |
| 5.5 | 实现 `SclGooseTransformer` | 输出与 `IcdGooseImporter` 一致 |
| 5.6 | 实现 `SclReportTransformer` | ReportControl 正确提取 |

### Phase 6: 服务层与 API (2 天) [P1 🟡]

**目标**: 实现 SclImportService + Web API

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 6.1 | 实现 `SclServiceContainer` | DI 容器可注入 Mock |
| 6.2 | 实现 `SclFileManager` | 上传/列表/删除正常 |
| 6.3 | 实现 `SclImportService` | 完整导入流程正常 |
| 6.4 | 实现 SCL Web API | 13 个端点 | CRUD + 上传/浏览/导入/对比 |
| 6.5 | 修改 `import_points.py` | 现有接口行为不变 |

### Phase 7: 异步导出 + 进度反馈 (1 天) [P2 🟢]

**目标**: 大模型导出不阻塞

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 7.1 | 实现 `ExportTask` | 异步任务状态 |
| 7.2 | 实现双模式导出 | 小模型流式/大模型异步 |
| 7.3 | 实现进度查询端点 | `/export-model-progress` |
| 7.4 | 前端进度条 | `ModelExportDialog.vue` |

### Phase 8: 迁移与增强 (2 天) [P2 🟢]

**目标**: 旧模块迁移为薄封装，增强高级功能

| # | 任务 | 产出 | 验收标准 |
|---|------|------|----------|
| 8.1 | 迁移 `IcdPointImporter` | 接口不变，内部委托 SclParser |
| 8.2 | 迁移 `IcdGooseImporter` | 接口不变，内部委托 SclParser |
| 8.3 | 实现 `SclServerModelBuilder` | SclDocument → IedModel |
| 8.4 | 增强 `FilesPlugin` | 文件列表可用 |

---

## 9. 迁移兼容性

### 9.1 向后兼容保证

| 接口 | 保证 |
|------|------|
| `IcdPointImporter.import_from_icd()` | 签名和行为不变 |
| `IcdGooseImporter.parse_icd()` | 签名和行为不变 |
| `/api/channels/import-icd` | 行为不变 |
| `DataModelsPlugin.discover_model()` | 返回值格式不变 |
| `IEC61850Client.model_exporter` | 仍可调用，内部使用 IedModel |
| `data/61850icd/` 目录 | 文件路径不变 |

### 9.2 渐进迁移路径

```
阶段 1 (Phase 1-3): 新增 model/ + 修改 DataModelsPlugin/ModelExporterPlugin
  ┌─────────────────────┐    ┌─────────────────────────┐
  │ DataModelsPlugin    │───▶│ ModelDiscoveryService    │  在线发现统一
  │ ModelExporterPlugin │───▶│ IedModel (缓存)          │
  └─────────────────────┘    └─────────────────────────┘

阶段 2 (Phase 4-6): 新增 scl/ 模块，与旧模块并行
  ┌─────────────────────┐    ┌─────────────────────────┐
  │ IcdPointImporter    │    │ SclParser               │  离线解析统一
  │ IcdGooseImporter    │    │ SclPointTransformer     │
  │ (旧，不修改)         │    │ (新，独立运行)            │
  └─────────────────────┘    └─────────────────────────┘

阶段 3 (Phase 8): 旧模块改为薄封装
  ┌─────────────────────┐    ┌─────────────────────────┐
  │ IcdPointImporter    │───▶│ SclParser               │
  │ (薄封装，委托)       │    │ SclPointTransformer     │
  └─────────────────────┘    └─────────────────────────┘
```

---

## 10. 设计模式总览

| 模式 | 应用位置 | 解决的问题 |
|------|----------|------------|
| **Builder** | `IedModelBuilder` | 分离模型构建与表示，支持流式构建 |
| **Strategy** | `JsonExporter` / `CsvExporter` / `IcdExporter` | 导出策略可替换，新增格式无需修改消费方 |
| **Facade** | `ModelDiscoveryService` / `SclImportService` | 简化复杂子系统的使用 |
| **Protocol** | `ModelExporter` / `SclParserProtocol` / `ValidationRule` | 结构化子类型，松耦合 |
| **Frozen Dataclass** | `IedModel` / `DARef` / `DORef` | 不可变值对象，线程安全 |
| **cached_property** | `IedModel.point_refs` / `IedModel.summary` | 派生属性延迟计算 |
| **Context Manager** | `_error_guard()` | 统一容错策略 |
| **Generator** | `iter_da_leaves()` / `export_streaming()` | 惰性求值，内存 O(1) |
| **Result** | `ValidationResult` | 替代异常处理校验结果 |
| **Registry** | `EXPORTERS` / `ValidationRuleRegistry` | 策略注册与查找 |
| **Null Object** | `ValidationResult.empty()` | 无错误时返回有效空对象 |
| **Background Task** | 临时文件清理 | 资源延迟释放 |
| **Bridge** | `build_registry_from_model()` | IedModel → PointRegistry 桥接 |

---

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| `frozen dataclass` 构建不便 | 低 | 中 | 使用 Builder 模式在构建阶段使用可变对象，构建完成产出不可变对象 |
| `pyiec61850` 非线程安全 | 高 | 中 | `ModelDiscoveryService` 串行遍历，导出器不调用 pyiec61850 API |
| SCL 格式差异大 | 高 | 中 | `NamespaceHelper` 兼容两种格式；`SclParser` 对缺失属性使用默认值 |
| 与现有 Importer 行为不一致 | 中 | 高 | Phase 5 对比验证 + 回归测试 |
| 大型 SCL 文件性能 | 中 | 中 | `slots=True` 减少内存；后续引入 `iterparse` 流式解析 |
| 前端异步轮询开销 | 低 | 低 | WebSocket 推送或 SSE 替代 |

---

## 12. 验收标准

### Phase 1 (核心)
- [ ] 连接 IED 后 `IedModel` 被正确缓存
- [ ] 导出模型时不再重新调用 `IedConnection_*` API
- [ ] `PointRegistry` 从 `IedModel` 派生的数据与原 `DataModelsPlugin.discover_model()` 一致
- [ ] 所有导出格式 (JSON/CSV/ICD/XML/Tree) 输出与修改前一致

### Phase 2 (导出)
- [ ] 导出器拆分为独立 Strategy 类
- [ ] `JsonStreamWriter` 可流式写入大型模型
- [ ] 临时文件在导出完成后自动清理

### Phase 3 (前端)
- [ ] 导出不再出现 `Converting circular structure to JSON` 错误

### Phase 4-5 (SCL)
- [ ] `SclParser.parse_file("KG_BAMS.icd")` 成功构建 `SclDocument`
- [ ] `SclPointTransformer` 输出与 `IcdPointImporter` 一致
- [ ] `SclGooseTransformer` 输出与 `IcdGooseImporter` 一致
- [ ] 校验器能检测引用缺失、DataSet 为空等错误

### 最终验收
- [ ] 模型发现只执行一次 (连接时)
- [ ] 5000 DO 模型导出成功率 > 95%
- [ ] 5000 DO 模型导出耗时 < 5s (使用缓存模型)
- [ ] 大型 SCL 文件 (5MB+) 解析时间 < 3s
- [ ] 现有功能无回归
