"""统一模型发现服务 — 一次发现，多处消费

核心变更:
- 连接时发现模型 → 构建 IedModel → 缓存
- 导出时直接使用缓存的 IedModel → 不再重新发现
- PointRegistry 从 IedModel 派生 → 不再独立发现

ModelDiscoveryService 是调用 pyiec61850 API 的唯一入口。
"""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
import time
from typing import Any, Protocol

from ..core.linked_list import get_list_from_linked_list
from ..core.native_calls import call_gil_safe
from ..defs import HAS_IEC61850, AcsiClass
from ..defs.address import extract_ln_class, infer_fc_from_address, infer_iec_type_from_address
from ..defs.da_patterns import (
    BDA_TYPE_MAP,
    DA_PATTERNS,
    ENC_DO_DA_TYPE_OVERRIDE,
    EXTRA_DA_INFO,
    KNOWN_BDA_FALLBACK_ONLINE,
    SKIP_DA_NAMES,
    STRUCT_DA_EXPAND_ONLINE,
)
from ..defs.ln_classes import (
    SIGNAL_DOS,
    SKIP_SYSTEM_DOS,
    YC_LN_CLASSES,
    YK_LN_CLASSES,
    YT_LN_CLASSES,
    YX_LN_CLASSES,
)
from ..defs.mms_types import MmsType, infer_mms_type_from_path, mms_type_from_native
from ..log import log
from ..plugins.datasets.directory import browse_dataset_members
from .ied_model import (
    DARef,
    DataSetRef,
    DORef,
    GoCBRef,
    IedModel,
    LDModel,
    LNModel,
    RCBRef,
    compute_point_refs,
)

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class DiscoveryProgress(Protocol):
    """发现进度回调协议"""

    def __call__(self, phase: str, current: int, total: int, message: str) -> None: ...


# ========== Builder 模式: 可变构建 → 不可变产出 ==========


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
            name=self.name,
            ln_class=self.ln_class,
            ref=self.ref,
            dos=tuple(self._dos),
            datasets=tuple(self._datasets),
            rcb_list=tuple(self._rcbs),
            gocb_list=tuple(self._gocbs),
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
            name=self.name,
            inst=self.inst,
            lns=tuple(ln.build() for ln in self._lns),
        )


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
        lds = tuple(ld.build() for ld in self._lds)
        return IedModel(
            host=self._host,
            port=self._port,
            discover_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            lds=lds,
            _point_refs=compute_point_refs(lds),
        )


# ========== 统一模型发现服务 ==========


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

    def __init__(self, skip_non_lln0: bool = True):
        self._model: IedModel | None = None
        self._model_timestamp: float = 0.0
        self._skip_non_lln0 = skip_non_lln0
        # 结构体子 DA 发现缓存: da_full_ref → [DARef]
        # 不同 DO 的同一 DA 名（如 mag）可能有不同的子属性组合：
        #   Temp001.mag → [f]（浮点测量值）
        #   SglMaxVolNo.mag → [i]（整型状态值）
        # 故使用完整引用路径（da_full_ref）而非 DA 名称作为缓存键。
        self._struct_sub_da_cache: dict[str, list[DARef]] = {}
        self._type_probe_cache: dict[tuple[str, str], MmsType] = {}
        self._type_probe_stats: dict[str, int] = {
            "total": 0,
            "spec": 0,
            "runtime": 0,
            "static": 0,
            "unknown": 0,
            "failed": 0,
        }
        # Some IEDs expose the API but reject every variable-specification
        # request. Stop probing after a sustained failure streak instead of
        # paying one extra MMS round trip for every DA in a large model.
        self._variable_spec_failure_limit = 32
        self._variable_spec_failures = 0
        self._variable_spec_disabled = False

    @property
    def model(self) -> IedModel | None:
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
        progress: DiscoveryProgress | None = None,
    ) -> IedModel:
        """在线发现 IED 完整数据模型

        遍历 LD → LN → DO/DS/RCB/GoCB → DA/BDA，构建不可变 IedModel。

        如果已有缓存模型，直接返回，不再重新遍历。

        Args:
            connection: Iec61850Connection 实例
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
        self._type_probe_cache.clear()
        self._type_probe_stats = {
            "total": 0,
            "spec": 0,
            "runtime": 0,
            "static": 0,
            "unknown": 0,
            "failed": 0,
        }
        self._variable_spec_failures = 0
        self._variable_spec_disabled = False

        # 提取底层 IedConnection
        conn = self._resolve_connection(connection)

        # 获取 LD 列表
        ld_names: list[str] = []
        with self._error_guard("获取逻辑设备列表", on_error):
            ld_names = self._browse_logical_devices(conn)

        if not ld_names:
            log.warning("未发现任何逻辑设备")
            self._model = IedModel()
            return self._model

        # 保存服务端实际 MMS domain，后续 DataSet 引用构建以此为准，
        # 避免错误的配置 model_name 被重复拼到完整 LD 名称前。
        if hasattr(connection, "_discovered_lds"):
            connection._discovered_lds = list(ld_names)

        host = getattr(connection, "ip", "")
        port = getattr(connection, "port", 102)
        builder = IedModelBuilder(host=host, port=port)

        total_lds = len(ld_names)
        for i, ld_name in enumerate(ld_names):
            progress and progress("discovering", i * 1000, total_lds * 1000, f"发现 LD: {ld_name}")

            def update_ld_progress(fraction: float, message: str, *, ld_index: int = i) -> None:
                if progress is None:
                    return
                completed = ld_index * 1000 + round(min(max(fraction, 0.0), 1.0) * 1000)
                progress("discovering", completed, total_lds * 1000, message)

            with self._error_guard(f"LD {ld_name}", on_error):
                self._discover_ld(
                    conn,
                    builder,
                    ld_name,
                    max_depth=max_depth,
                    on_error=on_error,
                    progress=update_ld_progress,
                )
            progress and progress(
                "discovering",
                (i + 1) * 1000,
                total_lds * 1000,
                f"已发现 LD: {ld_name}",
            )

        self._model = builder.build()
        self._model_timestamp = time.time()

        elapsed = time.time() - start_time
        log.info(f"统一模型发现完成, 耗时 {elapsed:.2f}s, {self._model.summary}, MMS类型统计={self._type_probe_stats}")
        return self._model

    def _probe_mms_type(self, conn, ref: str, fc: str, fallback: MmsType) -> MmsType:
        """Resolve and cache a native MMS type without unsafe control reads.

        Variable specifications are queried first because they expose the wire
        type without reading the value and therefore also work for FC=CO. Older
        bindings that do not expose this API retain the runtime/static fallback.
        """
        key = (ref, fc)
        cached = self._type_probe_cache.get(key)
        if cached is not None:
            return cached

        self._type_probe_stats["total"] += 1
        specified_type = self._probe_variable_spec_type(conn, ref, fc)
        if specified_type is not None:
            self._type_probe_stats["spec"] += 1
            self._type_probe_cache[key] = specified_type
            return specified_type

        if fc == "CO":
            resolved = fallback
            self._type_probe_stats["static" if resolved is not MmsType.UNKNOWN else "unknown"] += 1
            self._type_probe_cache[key] = resolved
            return resolved

        value = None
        try:
            fc_value = getattr(iec61850, f"IEC61850_FC_{fc}", None)
            if fc_value is None:
                raise ValueError(f"unsupported FC: {fc}")
            result = call_gil_safe(iec61850, "IedConnection_readObject", conn, ref, fc_value)
            if isinstance(result, (list, tuple)):
                value = result[0] if result else None
                error = result[1] if len(result) > 1 else 0
            else:
                value = result
                error = 0
            if error == iec61850.IED_ERROR_OK and value is not None:
                resolved = mms_type_from_native(int(iec61850.MmsValue_getType(value)), iec61850)
                if resolved not in (MmsType.UNKNOWN, MmsType.DATA_ACCESS_ERROR):
                    self._type_probe_stats["runtime"] += 1
                    self._type_probe_cache[key] = resolved
                    return resolved
        except Exception as e:
            log.debug(f"MMS 类型探测失败: ref={ref}, fc={fc}, error={e}")
        finally:
            if value is not None:
                with contextlib.suppress(Exception):
                    iec61850.MmsValue_delete(value)

        self._type_probe_stats["failed"] += 1
        resolved = fallback
        self._type_probe_stats["static" if resolved is not MmsType.UNKNOWN else "unknown"] += 1
        self._type_probe_cache[key] = resolved
        return resolved

    def _probe_mms_type_across_fcs(self, conn, ref: str, preferred_fc: str) -> tuple[str, MmsType | None]:
        """Resolve an unknown DA's FC and MMS type from variable specifications."""
        candidates = (
            preferred_fc,
            "MX",
            "ST",
            "CO",
            "CF",
            "DC",
            "SP",
            "SG",
            "SE",
            "SV",
            "EX",
            "BL",
            "OR",
            "SR",
            "US",
            "MS",
        )
        seen: set[str] = set()
        for fc in candidates:
            if not fc or fc in seen:
                continue
            seen.add(fc)
            key = (ref, fc)
            cached = self._type_probe_cache.get(key)
            if cached is not None:
                return fc, cached
            specified_type = self._probe_variable_spec_type(conn, ref, fc)
            if specified_type is None:
                continue
            self._type_probe_stats["total"] += 1
            self._type_probe_stats["spec"] += 1
            self._type_probe_cache[key] = specified_type
            return fc, specified_type
        return preferred_fc, None

    def _probe_variable_spec_type(self, conn, ref: str, fc: str) -> MmsType | None:
        if self._variable_spec_disabled:
            return None

        resolved = self._query_variable_spec_type(conn, ref, fc)
        if resolved is not None:
            self._variable_spec_failures = 0
            return resolved

        self._variable_spec_failures += 1
        if self._variable_spec_failures >= self._variable_spec_failure_limit:
            self._variable_spec_disabled = True
            log.info(
                f"连续变量规格探测失败，当前发现任务将改用运行时/静态类型推断 (failures={self._variable_spec_failures})"
            )
        return None

    @staticmethod
    def _query_variable_spec_type(conn, ref: str, fc: str) -> MmsType | None:
        """Query the server's MMS variable specification when supported."""
        get_spec = getattr(iec61850, "IedConnection_getVariableSpecification", None)
        get_type = getattr(iec61850, "MmsVariableSpecification_getType", None)
        destroy_spec = getattr(iec61850, "MmsVariableSpecification_destroy", None)
        fc_value = getattr(iec61850, f"IEC61850_FC_{fc}", None)
        if not callable(get_spec) or not callable(get_type) or fc_value is None:
            return None

        spec = None
        try:
            result = get_spec(conn, ref, fc_value)
            if isinstance(result, (list, tuple)):
                spec = result[0] if result else None
                error = result[1] if len(result) > 1 else 0
            else:
                spec = result
                error = 0
            if error != iec61850.IED_ERROR_OK or spec is None:
                return None

            resolved = mms_type_from_native(int(get_type(spec)), iec61850)
            if resolved in (MmsType.UNKNOWN, MmsType.DATA_ACCESS_ERROR):
                return None
            return resolved
        except Exception as e:
            log.debug(f"MMS 变量类型规格读取失败: ref={ref}, fc={fc}, error={e}")
            return None
        finally:
            if spec is not None and callable(destroy_spec):
                with contextlib.suppress(Exception):
                    destroy_spec(spec)

    @staticmethod
    def _resolve_connection(connection: Any) -> Any:
        """从 Iec61850Connection 或直接 IedConnection 中提取底层连接"""
        if hasattr(connection, "connection"):
            return connection.connection
        return connection

    @contextmanager
    def _error_guard(self, ref: str, on_error: str = "skip"):
        """节点发现错误守卫 — Context Manager 模式"""
        try:
            yield
        except TimeoutError:
            # Operation deadlines are control flow, not a skippable node error.
            raise
        except Exception as e:
            log.warning(f"发现 {ref} 时出错: {e}")
            if on_error == "abort":
                raise

    # ===== LD 发现 =====

    def _discover_ld(
        self,
        conn,
        builder: IedModelBuilder,
        ld_name: str,
        *,
        max_depth: int,
        on_error: str,
        progress=None,
    ) -> None:
        """分两阶段发现单个 LD：先构建完整模型，再解析 DataSet 等引用资源。"""
        ld_builder = builder.add_ld(ld_name, ld_name)

        ln_names: list[str] = []
        with self._error_guard(f"LN 列表 {ld_name}", on_error):
            ln_names = self._browse_logical_nodes(conn, ld_name)

        logical_nodes: list[tuple[str, str, _LNBuilder]] = []
        for ln_name in ln_names:
            ln_ref = f"{ld_name}/{ln_name}"
            ln_class = extract_ln_class(ln_name) or ""
            ln_builder = ld_builder.add_ln(ln_name, ln_class, ln_ref)
            logical_nodes.append((ln_name, ln_ref, ln_builder))

        # 第一阶段只发现完整 LD/LN/DO/DA 模型。DataSet 是模型引用的子集，
        # 不能反向定义数据类型，也不能作为模型发现的数据源。
        logical_node_count = max(len(logical_nodes), 1)
        for ln_index, (ln_name, ln_ref, ln_builder) in enumerate(logical_nodes):
            with self._error_guard(f"LN {ln_ref}", on_error):

                def update_do_progress(
                    current: int,
                    total: int,
                    do_name: str,
                    *,
                    current_ln_index: int = ln_index,
                    current_ln_ref: str = ln_ref,
                ) -> None:
                    if progress is None:
                        return
                    ln_fraction = current / total if total > 0 else 1.0
                    fraction = (current_ln_index + ln_fraction) / logical_node_count
                    progress(fraction, f"发现 DO: {current_ln_ref}.{do_name} ({current}/{total})")

                discover_args = (conn, ld_name, ln_ref, ln_name)
                if progress is None:
                    discovered_objects = self._discover_data_objects(*discover_args, max_depth=max_depth)
                else:
                    discovered_objects = self._discover_data_objects(
                        *discover_args,
                        max_depth=max_depth,
                        progress=update_do_progress,
                    )
                for do in discovered_objects:
                    ln_builder.add_do(do)

        # 第二阶段在模型已经存在的前提下解析 DataSet/RCB/GoCB。
        # DataSet 成员后续必须回到完整模型中校验，读取阶段才允许使用。
        for ln_name, ln_ref, ln_builder in logical_nodes:
            with self._error_guard(f"资源 {ln_ref}", on_error):
                if ln_name == "LLN0" or not self._skip_non_lln0:
                    for dataset in self._discover_datasets(conn, ld_name, ln_ref):
                        ln_builder.add_dataset(dataset)

                # RCB
                for rcb in self._discover_rcbs(conn, ld_name, ln_ref):
                    ln_builder.add_rcb(rcb)

                # GoCB — GOOSE 控制块仅存在于 LLN0, 跳过其他 LN
                if ln_name == "LLN0" or not self._skip_non_lln0:
                    for gocb in self._discover_gocbs(conn, ld_name, ln_ref):
                        ln_builder.add_gocb(gocb)

    # ===== 底层 pyiec61850 调用 (唯一调用点) =====

    @staticmethod
    def _browse_logical_devices(conn) -> list[str]:
        try:
            result = iec61850.IedConnection_getLogicalDeviceList(conn)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                ld_list, error = result[0], result[1]
                if error != iec61850.IED_ERROR_OK:
                    return []
            else:
                ld_list = result
            return get_list_from_linked_list(ld_list) if ld_list is not None else []
        except Exception as e:
            log.warning(f"获取逻辑设备列表异常: {e}")
            return []

    @staticmethod
    def _browse_logical_nodes(conn, ld_name: str) -> list[str]:
        try:
            result = iec61850.IedConnection_getLogicalDeviceDirectory(conn, ld_name)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                ln_list, error = result[0], result[1]
                if error != iec61850.IED_ERROR_OK:
                    return []
            else:
                ln_list = result
            return get_list_from_linked_list(ln_list) if ln_list is not None else []
        except Exception as e:
            log.warning(f"获取逻辑节点列表异常: {ld_name}, {e}")
            return []

    def _discover_data_objects(
        self,
        conn,
        ld_name: str,
        ln_ref: str,
        ln_name: str,
        max_depth: int,
        progress=None,
    ) -> list[DORef]:
        """发现 LN 下所有 DO 及其 DA/BDA"""
        do_refs = []

        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, AcsiClass.DATA_OBJECT)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                do_list, error = result[0], result[1]
                if error != iec61850.IED_ERROR_OK:
                    return []
            else:
                do_list = result
            do_names = get_list_from_linked_list(do_list) if do_list is not None else []
        except Exception as e:
            log.warning(f"获取数据对象列表异常: {ln_ref}, {e}")
            return []

        total_dos = len(do_names)
        for do_index, do_name in enumerate(do_names, start=1):
            do_ref = f"{ln_ref}.{do_name}"
            cdc, frame_type = self._infer_cdc_and_frame_type(do_name, ln_name)

            # 发现 DA
            das = self._discover_data_attributes(conn, do_ref, do_name, ln_name, frame_type, max_depth=max_depth)

            # 某些厂商使用非标准 LN class（如 CTRL），无法仅靠 LN/DO 名称
            # 推断 CDC。此时以在线发现到的主值 DA 结构为准。
            # setMag 是 ASG 的结构化设定值，子属性可能是 f 或 i。
            if any(da.name == "setMag" for da in das):
                cdc = "ASG"
                frame_type = 3

            do_refs.append(
                DORef(
                    name=do_name,
                    ref=do_ref,
                    cdc=cdc,
                    frame_type=frame_type,
                    das=tuple(das),
                )
            )
            if progress is not None:
                progress(do_index, total_dos, do_name)

        return do_refs

    # q/t/dU 是 IEC 61850 固有属性, 不动态发现, 默认硬编码创建
    # q 和 t 展开为子 DA (如 q.validity, t.seconds), 父结构体不能直接 MMS 读取
    _DEFAULT_META_DAS: tuple[tuple[str, str, str, str], ...] = (
        ("q", "q", "MX", "integer"),  # 品质 (Quality struct → 展开子 DA)
        ("t", "t", "MX", "timestamp"),  # 时标 (Timestamp struct → 展开子 DA)
        ("dU", "dU", "DC", "string"),  # 描述 (Description)
    )

    def _discover_data_attributes(
        self,
        conn,
        do_ref: str,
        do_name: str,
        ln_name: str,
        do_frame_type: int,
        max_depth: int = 10,
    ) -> list[DARef]:
        """发现 DO 下所有 DA

        q/t/dU 是 IEC 61850 固有属性，不动态发现，默认硬编码创建。
        即使 MMS getDataDirectory 调用失败，也会返回 q/t/dU 元数据 DA。
        """
        da_refs = []

        try:
            result = iec61850.IedConnection_getDataDirectory(conn, do_ref)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                da_list, error = result[0], result[1]
                if error != iec61850.IED_ERROR_OK:
                    da_list = None
            else:
                da_list = result
            da_names = get_list_from_linked_list(da_list) if da_list is not None else []
        except Exception as e:
            log.warning(f"获取数据属性列表异常: {do_ref}, {e}")
            da_names = []

        for da_name in da_names:
            # 跳过元数据 DA (q/t/dU 等), 稍后硬编码添加
            if da_name in SKIP_DA_NAMES:
                continue

            da_full_ref = f"{do_ref}.{da_name}"

            # 解析 DA 信息 (fc, iec_type, path)
            da_info = self._resolve_da_info(da_name, do_name, ln_name, do_frame_type)
            da_fc = da_info.fc
            specified_type = None
            if not da_fc:
                da_fc, specified_type = self._probe_mms_type_across_fcs(
                    conn,
                    da_full_ref,
                    self._infer_fc_from_da(da_name, do_frame_type),
                )

            # 递归发现 BDA (结构体 DA)
            sub_das: tuple[DARef, ...] = ()
            if da_name in STRUCT_DA_EXPAND_ONLINE and max_depth > 0:
                sub_das = tuple(
                    self._discover_sub_das(
                        conn,
                        da_full_ref,
                        da_fc,
                        f"{da_info.path}.",
                        depth=1,
                        max_depth=max_depth,
                    )
                )
            elif "." in da_info.path and da_name not in SKIP_DA_NAMES and max_depth > 0:
                # DA_PATTERNS 硬编码了子路径（如 mag→mag.f），但实际 IED
                # 可能用 mag.i（整型）替代 mag.f（浮点）。
                # 通过缓存 + 按需 MMS 发现来动态确定真实子 DA 结构。
                actual_sub_das = self._discover_struct_sub_das(conn, da_full_ref, da_name, da_info, do_frame_type)
                if actual_sub_das is not None:
                    sub_das = tuple(actual_sub_das)
            elif specified_type is MmsType.STRUCTURE and max_depth > 0:
                # 厂家自定义结构无需预置 DA 名称：变量类型规格确认其为
                # structure 后，再从服务端目录递归发现子项。
                sub_das = tuple(
                    self._discover_sub_das(
                        conn,
                        da_full_ref,
                        da_fc,
                        f"{da_info.path}.",
                        depth=1,
                        max_depth=max_depth,
                    )
                )

            # 当动态发现了实际子 DA（如 mag 下有 i 而非 f），
            # 使用真实子 DA 的路径和类型覆盖硬编码的默认值
            if sub_das:
                # Oper/SBOw/Cancel 是控制命令结构，目录顺序经常以 Check/T
                # 开头；其主值必须固定为 ctlVal，不能取第一个子属性。
                preferred_sub_da = None
                if da_name in ("Oper", "SBOw", "Cancel"):
                    preferred_sub_da = next((sub_da for sub_da in sub_das if sub_da.name == "ctlVal"), None)
                value_sub_da = preferred_sub_da or sub_das[0]
                effective_da_path = f"{da_name}.{value_sub_da.name}"
                effective_iec_type = value_sub_da.iec_type
                mms_type = MmsType.STRUCTURE
            else:
                effective_da_path = da_info.path
                effective_iec_type = da_info.iec_type
                fallback_mms_type = infer_mms_type_from_path(effective_da_path, effective_iec_type)
                mms_type = specified_type or self._probe_mms_type(
                    conn, f"{do_ref}.{effective_da_path}", da_fc, fallback_mms_type
                )

            da_refs.append(
                DARef(
                    name=da_name,
                    path=effective_da_path,
                    fc=da_fc,
                    iec_type=effective_iec_type,
                    mms_type=mms_type,
                    sub_das=sub_das,
                )
            )

        # 默认硬编码创建 q/t/dU (IEC 61850 固有属性)。控制对象的
        # Oper/SBOw 等 FC=CO 属性不具备可读的 q/t，不能为其伪造元数据。
        is_control_object = any(da.fc == "CO" or any(sub_da.fc == "CO" for sub_da in da.sub_das) for da in da_refs)

        # 即使 MMS 调用失败，也确保普通状态/测量 DO 包含这些元数据 DA
        # q 和 t 是结构化类型, 展开子 DA (如 q.validity, t.seconds) 以便 MMS 读取
        for da_name, da_path, da_fc, da_iec_type in self._DEFAULT_META_DAS:
            if is_control_object and da_name in ("q", "t"):
                continue
            meta_sub_das: tuple[DARef, ...] = ()
            if da_name in ("q", "t") and da_name in KNOWN_BDA_FALLBACK_ONLINE:
                bda_refs: list[DARef] = []
                for bda_name in KNOWN_BDA_FALLBACK_ONLINE[da_name]:
                    bda_iec_type = BDA_TYPE_MAP.get(bda_name, "unknown")
                    bda_refs.append(
                        DARef(
                            name=bda_name,
                            path=f"{da_path}.{bda_name}",
                            fc=da_fc,
                            iec_type=bda_iec_type,
                            mms_type=infer_mms_type_from_path(f"{da_path}.{bda_name}", bda_iec_type),
                        )
                    )
                meta_sub_das = tuple(bda_refs)
            meta_mms_type = self._probe_mms_type(
                conn,
                f"{do_ref}.{da_path}",
                da_fc,
                infer_mms_type_from_path(da_path, da_iec_type),
            )
            da_refs.append(
                DARef(
                    name=da_name,
                    path=da_path,
                    fc=da_fc,
                    iec_type=da_iec_type,
                    mms_type=meta_mms_type,
                    sub_das=meta_sub_das,
                )
            )

        return da_refs

    def _discover_sub_das(
        self,
        conn,
        parent_ref: str,
        parent_fc: str,
        path_prefix: str,
        *,
        depth: int = 1,
        max_depth: int = 10,
    ) -> list[DARef]:
        """递归发现子 DA — 带深度限制"""
        if depth > max_depth:
            log.warning(f"递归深度达到上限 {max_depth}, 停止展开: {parent_ref}")
            return []

        sub_das = []
        try:
            result = iec61850.IedConnection_getDataDirectory(conn, parent_ref)
            bda_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or bda_list is None:
                # 回退: 使用已知 BDA
                parent_name = parent_ref.split(".")[-1]
                if parent_name in KNOWN_BDA_FALLBACK_ONLINE:
                    for bda_name in KNOWN_BDA_FALLBACK_ONLINE[parent_name]:
                        bda_iec_type = BDA_TYPE_MAP.get(bda_name, "unknown")
                        bda_path = f"{path_prefix}{bda_name}"
                        sub_das.append(
                            DARef(
                                name=bda_name,
                                path=bda_path,
                                fc=parent_fc,
                                iec_type=bda_iec_type,
                                mms_type=infer_mms_type_from_path(bda_path, bda_iec_type),
                            )
                        )
                return sub_das

            bda_names = get_list_from_linked_list(bda_list)
            for bda_name in bda_names:
                bda_type = BDA_TYPE_MAP.get(bda_name, "unknown")
                bda_path = f"{path_prefix}{bda_name}"
                bda_mms_type = self._probe_mms_type(
                    conn,
                    f"{parent_ref}.{bda_name}",
                    parent_fc,
                    infer_mms_type_from_path(bda_path, bda_type),
                )
                sub_das.append(
                    DARef(
                        name=bda_name,
                        path=bda_path,
                        fc=parent_fc,
                        iec_type=bda_type,
                        mms_type=bda_mms_type,
                    )
                )

        except Exception as e:
            log.debug(f"发现子数据属性异常: {parent_ref}, {e}")

        return sub_das

    def _discover_struct_sub_das(
        self,
        conn,
        da_full_ref: str,
        da_name: str,
        da_info: DARef,
        do_frame_type: int,
    ) -> list[DARef] | None:
        """按需发现 struct DA 的实际子 DA，带完整引用缓存

        DA_PATTERNS 对 mag 等 struct DA 硬编码了子路径（mag→mag.f），
        但实际 IED 可能用 mag.i（整型）替代 mag.f（浮点）。

        使用 da_full_ref（如 "LD1/MMCL1.Temp001.mag"）作为缓存键，
        而非 da_name（如 "mag"），因为不同 DO 的同一 DA 名可能有
        不同的子属性（Temp001.mag→[f], SglMaxVolNo.mag→[i]）。

        Returns:
            list[DARef] — 发现成功时返回子 DA 列表
            None — 发现失败时返回 None，调用方沿用硬编码默认值
        """
        if da_full_ref in self._struct_sub_da_cache:
            cached = self._struct_sub_da_cache[da_full_ref]
            return list(cached) if cached else None

        fc = da_info.fc or self._infer_fc_from_da(da_name, do_frame_type)
        try:
            result = iec61850.IedConnection_getDataDirectory(conn, da_full_ref)
            sub_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error == iec61850.IED_ERROR_OK and sub_list is not None:
                sub_names = get_list_from_linked_list(sub_list)
                sub_das: list[DARef] = []
                base_path = da_info.path.split(".")[0]
                for sub_name in sub_names:
                    sub_path = f"{base_path}.{sub_name}"
                    sub_iec_type = BDA_TYPE_MAP.get(sub_name, "unknown")
                    sub_das.append(
                        DARef(
                            name=sub_name,
                            path=sub_path,
                            fc=fc,
                            iec_type=sub_iec_type,
                            mms_type=self._probe_mms_type(
                                conn,
                                f"{da_full_ref}.{sub_name}",
                                fc,
                                infer_mms_type_from_path(sub_path, sub_iec_type),
                            ),
                        )
                    )
                if sub_das:
                    self._struct_sub_da_cache[da_full_ref] = sub_das
                    # log.info(f"动态发现 struct DA '{da_full_ref}' 子结构: {[s.path for s in sub_das]}")
                    return sub_das
        except Exception as e:
            log.debug(f"动态发现 struct DA 子属性失败: {da_full_ref}, {e}")

        # 发现失败: 标记缓存为 None 避免重复尝试
        self._struct_sub_da_cache[da_full_ref] = []
        return None

    def _discover_datasets(self, conn, ld_name: str, ln_ref: str) -> list[DataSetRef]:
        """发现 LN 下所有 DataSet"""
        datasets = []

        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, AcsiClass.DATA_SET)
            ds_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or ds_list is None:
                return []

            ds_names = get_list_from_linked_list(ds_list)

            for ds_name in ds_names:
                ds_ref = f"{ln_ref}.{ds_name}"

                is_deletable = False
                try:
                    from ctypes import c_bool

                    is_deletable_obj = c_bool()
                    iec61850.IedConnection_getDataSetDirectory(conn, ds_ref, is_deletable_obj)
                    is_deletable = bool(is_deletable_obj.value)
                except Exception:
                    log.error(f"发现 DataSet {ds_ref} 是否可删除失败")

                members = self._discover_dataset_members(conn, ds_ref)
                datasets.append(
                    DataSetRef(
                        name=ds_name,
                        ref=ds_ref,
                        is_deletable=is_deletable,
                        members=tuple(members),
                    )
                )
        except Exception as e:
            log.debug(f"发现数据集异常: {ln_ref}, {e}")

        return datasets

    @staticmethod
    def _discover_dataset_members(conn, ds_ref: str) -> list[dict[str, str]]:
        """发现 DataSet 成员，复用客户端 DataSet 目录解析实现。"""
        try:
            return browse_dataset_members(iec61850, conn, ds_ref)
        except Exception as e:
            log.debug(f"发现 DataSet 成员异常: {ds_ref}, {e}")
            return []

    def _discover_rcbs(self, conn, ld_name: str, ln_ref: str) -> list[RCBRef]:
        """发现 LN 下所有 RCB (含 datSet, intgPd 等详情)

        通过 getRCBValues 读取 RCB 属性以获取 datSet 和 intgPd。
        每个 RCB 独立 try/except，单点失败不影响其他 RCB 发现。
        """
        rcbs = []
        for acsi_val, type_name, fc_seg in [
            (AcsiClass.URCB, "URCB", "RP"),
            (AcsiClass.BRCB, "BRCB", "BR"),
        ]:
            try:
                result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, acsi_val)
                rcb_list = result[0] if isinstance(result, (list, tuple)) else result
                error = result[1] if isinstance(result, (list, tuple)) else 0

                if error != iec61850.IED_ERROR_OK or rcb_list is None:
                    continue

                rcb_names = get_list_from_linked_list(rcb_list)
                for rcb_name in rcb_names:
                    dat_set, intg_pd = self._read_rcb_detail(conn, ld_name, ln_ref, rcb_name, fc_seg)
                    rcbs.append(
                        RCBRef(
                            name=rcb_name,
                            ref=f"{ln_ref}.{rcb_name}",
                            rcb_type=type_name,
                            dat_set=dat_set,
                            intg_pd=intg_pd,
                        )
                    )
            except Exception:
                pass
        return rcbs

    def _read_rcb_detail(self, conn, ld_name: str, ln_ref: str, rcb_name: str, fc_seg: str) -> tuple[str, int]:
        """读取 RCB 的 datSet 和 intgPd 属性

        使用完整参考路径(含 FC 段)读取 RCB 值。
        失败时静默返回空值，不阻断发现流程。

        Returns:
            (dat_set, intg_pd) 二元组
        """
        ln_name = ln_ref.split("/", 1)[-1] if "/" in ln_ref else ln_ref
        nref = f"{ld_name}/{ln_name}.{fc_seg}.{rcb_name}"
        rcb = None
        try:
            rcb = iec61850.ClientReportControlBlock_create(nref)
            if rcb is not None:
                result = call_gil_safe(iec61850, "IedConnection_getRCBValues", conn, nref, rcb)
                err = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if err == iec61850.IED_ERROR_OK:
                    dat_set = ""
                    try:
                        ds_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
                        if ds_ref:
                            ds_str = str(ds_ref)
                            if "$" in ds_str:
                                dat_set = ds_str.split("$", 1)[-1]
                            elif "." in ds_str:
                                dat_set = ds_str.rsplit(".", 1)[-1]
                            else:
                                dat_set = ds_str
                    except Exception:
                        pass

                    intg_pd = 0
                    try:
                        intg_pd = int(iec61850.ClientReportControlBlock_getIntgPd(rcb) or 0)
                    except Exception:
                        pass

                    return (dat_set, intg_pd)
        except Exception:
            pass
        finally:
            if rcb is not None:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        return ("", 0)

    def _discover_gocbs(self, conn, ld_name: str, ln_ref: str) -> list[GoCBRef]:
        """发现 LN 下所有 GoCB (含完整信息)"""
        gocbs = []

        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, AcsiClass.GOOSE)
            gocb_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or gocb_list is None:
                return []

            gocb_names = get_list_from_linked_list(gocb_list)
            for gocb_name in gocb_names:
                gocb = self._read_gocb_info(conn, ld_name, ln_ref, gocb_name)
                gocbs.append(gocb)
        except Exception:
            pass

        return gocbs

    def _read_gocb_info(self, conn, ld_name: str, ln_ref: str, cb_name: str) -> GoCBRef:
        """读取 GOOSE 控制块详细信息"""
        app_id = None
        dat_set = ""
        conf_rev = 0
        go_id = ""

        # libiec61850 的 getGoCBValues 要求引用含 FC 段 .GO.
        gocb_ref = f"{ld_name}/LLN0.GO.{cb_name}"
        gocb = None
        try:
            gocb = iec61850.ClientGooseControlBlock_create(gocb_ref)
            if gocb is not None:
                result = iec61850.IedConnection_getGoCBValues(conn, gocb_ref, gocb)
                err = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if err != iec61850.IED_ERROR_OK:
                    log.warning(f"getGoCBValues 失败: ref={gocb_ref}, err={err}")
                    with contextlib.suppress(Exception):
                        iec61850.ClientGooseControlBlock_destroy(gocb)
                    gocb = None
            else:
                log.warning(f"ClientGooseControlBlock_create 失败: ref={gocb_ref}")
        except Exception as e:
            log.warning(f"getGoCBValues 异常: ref={gocb_ref}, {type(e).__name__}: {e}")
            gocb = None

        if gocb is not None:
            try:
                appid_val = iec61850.ClientGooseControlBlock_getDstAddress_appid(gocb)
                if appid_val is not None:
                    app_id = int(appid_val)
            except Exception as e:
                log.debug(f"读取 GoCB appID 失败: {e}")
            try:
                dat_set = str(iec61850.ClientGooseControlBlock_getDatSet(gocb) or "")
            except Exception as e:
                log.debug(f"读取 GoCB datSet 失败: {e}")
            try:
                conf_rev = int(iec61850.ClientGooseControlBlock_getConfRev(gocb) or 0)
            except Exception as e:
                log.debug(f"读取 GoCB confRev 失败: {e}")
            try:
                go_id = str(iec61850.ClientGooseControlBlock_getGoID(gocb) or "")
            except Exception as e:
                log.debug(f"读取 GoCB goID 失败: {e}")
            with contextlib.suppress(Exception):
                iec61850.ClientGooseControlBlock_destroy(gocb)

        go_cb_ref = f"{ld_name}/LLN0$GO${cb_name}"
        return GoCBRef(
            name=cb_name,
            ref=f"{ln_ref}.{cb_name}",
            go_cb_ref=go_cb_ref,
            go_id=go_id,
            app_id=app_id,
            data_set_ref=dat_set,
            conf_rev=conf_rev,
        )

    # ===== 推断逻辑 (从 DataModelsPlugin 和 ModelExporter 合并) =====

    @staticmethod
    def _infer_cdc_and_frame_type(do_name: str, ln_name: str) -> tuple[str, int]:
        """推断 DO 的 CDC 和 frame_type"""
        # 简单地址模式: DO 名带前缀
        if do_name.startswith("MV_"):
            return "MV", 0
        elif do_name.startswith("SPS_"):
            return "SPS", 1
        elif do_name.startswith("SPC_"):
            return "SPC", 2
        elif do_name.startswith("APC_"):
            return "APC", 3

        ln_class = extract_ln_class(ln_name) or ""

        # 根据 DO 名称推断
        if do_name in ("Mod", "Beh", "Health"):
            return "ENC", -1
        if do_name == "NamPlt":
            return "LPL", -1
        if do_name in SKIP_SYSTEM_DOS or do_name in SIGNAL_DOS:
            return "", 1

        # 动态模型模式: 根据 LN class 推断
        if ln_class in YC_LN_CLASSES:
            return "", 0
        elif ln_class in YX_LN_CLASSES:
            return "", 1
        elif ln_class in YK_LN_CLASSES:
            return "", 2
        elif ln_class in YT_LN_CLASSES:
            return "", 3

        # DO 名称前缀推断
        if do_name.startswith(("TotW", "TotV", "TotA", "TotF", "TotPF", "TotQ")):
            return "", 0
        if do_name.startswith(("A", "V", "W", "Hz", "PF", "PhV", "PPV", "Amp", "Vol")):
            return "", 0
        if do_name.startswith(("St", "Ind", "Blk", "Sw")):
            return "", 1
        if do_name.startswith(("Ctl", "Pos")):
            return "", 2
        if do_name.startswith(("Spt", "ValW", "Csx")):
            return "", 3

        return "", -1

    @staticmethod
    def _resolve_da_info(da_name: str, do_name: str, ln_name: str, do_frame_type: int) -> DARef:
        """根据 DA 名称推断完整路径、FC 和类型"""
        if da_name in DA_PATTERNS:
            full_path, frame_type, iec_type = DA_PATTERNS[da_name]
            fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "SP"}
            return DARef(
                name=da_name,
                path=full_path,
                fc=fc_map.get(frame_type, ""),
                iec_type=iec_type,
            )

        if da_name in EXTRA_DA_INFO:
            full_path, fc, iec_type = EXTRA_DA_INFO[da_name]
            return DARef(name=da_name, path=full_path, fc=fc, iec_type=iec_type)

        if do_name in ENC_DO_DA_TYPE_OVERRIDE and da_name in ENC_DO_DA_TYPE_OVERRIDE[do_name]:
            return DARef(
                name=da_name,
                path=da_name,
                fc="ST" if da_name == "stVal" else "CO",
                iec_type=ENC_DO_DA_TYPE_OVERRIDE[do_name][da_name],
            )

        fc = infer_fc_from_address(da_name)
        iec_type = infer_iec_type_from_address(da_name)

        return DARef(name=da_name, path=da_name, fc=fc, iec_type=iec_type)

    @staticmethod
    def _infer_fc_from_da(da_name: str, do_frame_type: int) -> str:
        """根据 DA 名称和 DO 帧类型推断 FC"""
        if da_name in DA_PATTERNS:
            frame_type = DA_PATTERNS[da_name][1]
            return {0: "MX", 1: "ST", 2: "CO", 3: "SP"}.get(frame_type, "")
        if da_name in EXTRA_DA_INFO:
            return EXTRA_DA_INFO[da_name][1]
        return {0: "MX", 1: "ST", 2: "CO", 3: "SP"}.get(do_frame_type, "")
