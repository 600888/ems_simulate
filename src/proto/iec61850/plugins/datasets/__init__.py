"""IEC 61850 DataSet 发现与 DataSet 优先的批量读取门面。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import contextlib
import threading
import time
from typing import Any

from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
from ...defs.address import infer_fc_from_address, infer_iec_type_from_address
from ...defs.constants import HAS_IEC61850, IEC_TYPE_UNKNOWN
from ...defs.mms_types import iec_type_from_mms_type
from ...log import log
from .catalog import DatasetCatalog, DatasetReadPlanner, normalize_dataset_ref, normalize_point_ref
from .directory import browse_dataset_members
from .models import DatasetBatchStats, DatasetDescriptor, DatasetReadResult
from .transport import DatasetTransport

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850
else:
    iec61850 = None


FallbackReader = Callable[[Sequence[str], Mapping[str, str] | None], dict[str, Any]]
ProgressCallback = Callable[[str, int, int, str], None]


class DataSetsPlugin:
    """统一编排 DataSet 发现、目录规划和原生批读。"""

    def __init__(self):
        """初始化连接无关状态；原生依赖由插件注册表稍后注入。"""
        self._connection = None
        self._registry = None
        self._client = None
        self._initialized = False
        self._dataset_members_cache: dict[str, list[dict[str, Any]]] = {}
        self._catalog: DatasetCatalog | None = None
        self._catalog_signature: tuple[Any, ...] | None = None
        self._catalog_lock = threading.RLock()
        self._transport: DatasetTransport | None = None

    @property
    def name(self) -> str:
        return "datasets"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        self._connection = connection
        self._registry = kwargs.get("registry")
        self._client = kwargs.get("client")
        self._transport = DatasetTransport(connection, iec61850)
        self._initialized = True
        log.info("DataSets 插件已初始化")

    def shutdown(self) -> None:
        self.invalidate_catalog()
        self._connection = None
        self._registry = None
        self._client = None
        self._transport = None
        self._initialized = False

    def invalidate_catalog(self, *, clear_member_cache: bool = True) -> None:
        """原子清除模型索引；断线时同时清目录，在线刷新时可保留新目录。"""
        with self._catalog_lock:
            self._catalog = None
            self._catalog_signature = None
            if clear_member_cache:
                self._dataset_members_cache.clear()

    def discover_datasets(self) -> list[dict[str, Any]]:
        """发现远端持久 DataSet 及其有序 FCDA 成员。"""
        if not self._connection or not self._connection.is_connected:
            return []
        try:
            logical_devices = self._connection.browse_logical_devices()
        except Exception as exc:
            log.error(f"发现 DataSet 时获取逻辑设备列表失败: {exc}")
            return []

        datasets: list[dict[str, Any]] = []
        with self._connection.native_operation() as conn:
            if conn is None:
                return []
            for logical_device in logical_devices:
                try:
                    result = iec61850.IedConnection_getLogicalDeviceDataSets(conn, logical_device)
                    refs = result[0] if isinstance(result, (list, tuple)) else result
                    error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0
                    if error != iec61850.IED_ERROR_OK or refs is None:
                        continue
                    for raw_ref in get_list_from_linked_list(refs):
                        ref = self._catalog_ref(str(raw_ref), str(logical_device))
                        members = browse_dataset_members(iec61850, conn, self._connection.build_dataset_ref(ref))
                        self._cache_members(ref, members)
                        rest = ref.split("/", 1)[1] if "/" in ref else ref
                        datasets.append(
                            {
                                "ref": ref,
                                "name": rest.rsplit("$", 1)[-1],
                                "ld": logical_device,
                                "ln": rest.split("$", 1)[0],
                                "member_count": len(members),
                                "members": members,
                            }
                        )
                except Exception as exc:
                    log.debug(f"发现逻辑设备 {logical_device} 的 DataSet 失败: {exc}")
        self.invalidate_catalog(clear_member_cache=False)
        log.info(f"DataSet 发现完成, 共发现 {len(datasets)} 个 DataSet")
        return datasets

    @staticmethod
    def _catalog_ref(raw_ref: str, logical_device: str) -> str:
        """将设备返回的相对/完整 DataSet 名称统一为目录引用。"""
        if "/" in raw_ref:
            _, rest = raw_ref.split("/", 1)
            return normalize_dataset_ref(f"{logical_device}/{rest}")
        return normalize_dataset_ref(f"{logical_device}/{raw_ref}")

    def browse_dataset_directory(self, dataset_ref: str) -> list[dict[str, Any]]:
        """返回一个 DataSet 中有序且已规范化的 FCDA 条目。"""
        if not self._connection or not self._connection.is_connected:
            return []
        cache_key = self._connection.build_dataset_ref(normalize_dataset_ref(dataset_ref))
        cached = self._dataset_members_cache.get(cache_key)
        if cached is not None:
            return [dict(member) for member in cached]
        with self._connection.native_operation() as conn:
            if conn is None:
                return []
            members = browse_dataset_members(iec61850, conn, cache_key)
        self._cache_members(dataset_ref, members)
        return [dict(member) for member in members]

    def _cache_members(self, dataset_ref: str, members: list[dict[str, Any]]) -> None:
        """按完整 DataSet 引用缓存成员目录，避免重复 MMS 浏览。"""
        if not self._connection or not members:
            return
        cache_key = self._connection.build_dataset_ref(normalize_dataset_ref(dataset_ref))
        self._dataset_members_cache[cache_key] = [dict(member) for member in members]

    def _catalog_data(self) -> list[dict[str, Any]]:
        """从统一注册表取得兼容旧接口的 DataSet 字典列表。"""
        if self._registry is None:
            return []
        return list(getattr(self._registry, "discovered_datasets", ()) or ())

    def _get_catalog(self) -> DatasetCatalog:
        """按目录签名惰性构造不可变索引，并以原子方式替换缓存。"""
        datasets = self._catalog_data()
        signature = self._make_signature(datasets)
        with self._catalog_lock:
            if self._catalog is not None and signature == self._catalog_signature:
                return self._catalog
            model = getattr(self._client, "model", None) if self._client is not None else None
            # 在线 IedModel 中的 LD 已是完整 MMS domain；只有 ICD 离线模型
            # 缺少在线 domain 信息时，才使用配置 model_name 补齐前缀。
            model_name = "" if model is not None else str(getattr(self._connection, "model_name", "") or "")
            catalog = DatasetCatalog.from_sources(
                datasets,
                registry=self._registry,
                model=model,
                model_name=model_name,
            )
            self._catalog = catalog
            self._catalog_signature = signature
            return catalog

    @staticmethod
    def _make_signature(datasets: Sequence[Mapping[str, Any]]) -> tuple[Any, ...]:
        """生成只包含规划相关字段的稳定目录签名。"""
        return tuple(
            (
                dataset.get("ref", ""),
                tuple(
                    (member.get("ref", ""), member.get("fc", ""), member.get("mms_type", ""))
                    for member in (dataset.get("members", ()) or ())
                ),
            )
            for dataset in datasets
        )

    def read_points_batch(
        self,
        addresses: Sequence[str],
        fc_map: Mapping[str, str] | None,
        fallback: FallbackReader,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """按计划批读 DataSet，并且只对未返回的测点执行单点回退。"""
        requested = tuple(dict.fromkeys(str(address) for address in addresses))
        if not requested or not self._connection or not self._connection.ensure_connected():
            return {}

        started = time.perf_counter()
        catalog = self._get_catalog()
        plan = DatasetReadPlanner(catalog).plan(requested)
        dataset_total = len(plan.datasets)
        self._emit_progress(progress, "planning", 0, max(dataset_total, 1), f"计划读取 {dataset_total} 个 DataSet")
        results, request_count = self._execute_plan(plan.datasets, catalog, progress=progress)
        selected_dataset_count = len(plan.datasets)

        missing = tuple(address for address in requested if address not in results)
        if missing and self._connection.reconnect_if_unhealthy(
            f"dataset batch read {len(requested)} points, got {len(results)} values"
        ):
            self.invalidate_catalog()
            catalog = self._get_catalog()
            retry_plan = DatasetReadPlanner(catalog).plan(missing)
            retry_results, retry_count = self._execute_plan(
                retry_plan.datasets,
                catalog,
                progress=progress,
                phase="retry",
            )
            selected_dataset_count += len(retry_plan.datasets)
            results.update(retry_results)
            request_count += retry_count
            missing = tuple(address for address in requested if address not in results)

        fallback_count = len(missing)
        if missing:
            self._emit_progress(
                progress,
                "fallback",
                0,
                1,
                f"DataSet 未覆盖或读取失败，回退读取 {fallback_count} 个测点",
            )
            missing_fc = {address: fc_map[address] for address in missing if fc_map and address in fc_map}
            results.update(fallback(missing, missing_fc))
            self._emit_progress(progress, "fallback", 1, 1, f"回退读取完成，共 {fallback_count} 个测点")

        failed = sum(1 for address in requested if address not in results)
        elapsed_ms = (time.perf_counter() - started) * 1000
        stats = DatasetBatchStats(
            requested=len(requested),
            datasets=selected_dataset_count,
            covered=len(requested) - fallback_count,
            fallback=fallback_count,
            failed=failed,
            mms_requests=request_count + fallback_count,
            elapsed_ms=elapsed_ms,
        )
        log.info(
            "IEC61850 DataSet batch: "
            f"requested={stats.requested}, datasets={stats.datasets}, covered={stats.covered}, "
            f"fallback={stats.fallback}, failed={stats.failed}, requests={stats.mms_requests}, "
            f"elapsed={stats.elapsed_ms:.2f}ms"
        )
        # DataSet 可能包含本批未请求的其他成员。公开批读接口只返回调用方
        # 请求的地址，避免上层 Handler 意外生成额外 point.code。
        return {address: results[address] for address in requested if address in results}

    def _execute_plan(
        self,
        datasets: Sequence[DatasetDescriptor],
        catalog: DatasetCatalog,
        *,
        progress: ProgressCallback | None = None,
        phase: str = "dataset",
    ) -> tuple[dict[str, Any], int]:
        """每个选中 DataSet 只请求一次，合并成功值并缓存运行时类型。"""
        results: dict[str, Any] = {}
        request_count = 0
        if self._transport is None:
            return results, request_count
        total = len(datasets)
        for index, dataset in enumerate(datasets, start=1):
            read_result = self._transport.read(dataset)
            request_count += read_result.request_count
            for ref, value in read_result.values:
                for address in catalog.addresses_for_ref(ref):
                    results[address] = value
            self._cache_runtime_types(read_result, catalog)
            if read_result.errors:
                reason_counts: dict[str, int] = {}
                for error in read_result.errors:
                    reason_counts[error.reason] = reason_counts.get(error.reason, 0) + 1
                log.debug(
                    f"DataSet partial read: ref={dataset.ref}, values={len(read_result.values)}, "
                    f"errors={len(read_result.errors)}, reasons={reason_counts}"
                )
            self._emit_progress(
                progress,
                phase,
                index,
                total,
                f"已读取 DataSet {index}/{total}: {dataset.name or dataset.ref}",
            )
        return results, request_count

    @staticmethod
    def _emit_progress(
        progress: ProgressCallback | None,
        phase: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        """进度回调不得影响协议读取；UI 断开或回调异常时静默继续。"""
        if progress is None:
            return
        try:
            progress(phase, current, total, message)
        except Exception as exc:
            log.debug(f"DataSet 读取进度回调失败: {exc}")

    def _cache_runtime_types(self, result: DatasetReadResult, catalog: DatasetCatalog) -> None:
        """把 DataSet 返回的真实 MMS 类型回写测点注册表。"""
        if self._registry is None:
            return
        for ref, mms_type in result.runtime_types:
            for address in catalog.addresses_for_ref(ref):
                self._registry.set_mms_type(address, mms_type)
                self._registry.set_iec_type(address, iec_type_from_mms_type(mms_type).value)

    def read_dataset_values(
        self,
        dataset_ref: str,
        *,
        allow_member_fallback: bool = True,
    ) -> dict[str, Any]:
        """读取完整 DataSet；严格模式失败时不执行逐成员兼容回退。"""
        if not self._connection or not self._connection.ensure_connected():
            return {}
        catalog = self._get_catalog()
        model = getattr(self._client, "model", None) if self._client is not None else None
        model_name = "" if model is not None else str(self._connection.model_name or "")
        normalized = normalize_dataset_ref(dataset_ref, model_name)
        descriptor = next((item for item in catalog.datasets if item.ref == normalized), None)
        if descriptor is None:
            members = self.browse_dataset_directory(dataset_ref)
            descriptor_catalog = DatasetCatalog.from_sources(
                [{"ref": dataset_ref, "members": members}],
                registry=self._registry,
                model=model,
                model_name=model_name,
            )
            descriptor = descriptor_catalog.datasets[0] if descriptor_catalog.datasets else None
        if descriptor is None or self._transport is None:
            return self._read_dataset_values_by_members(dataset_ref) if allow_member_fallback else {}

        result = self._transport.read(descriptor)
        if result.member_values and (allow_member_fallback or not result.errors):
            return result.member_value_map
        if result.errors:
            reason_counts: dict[str, int] = {}
            for error in result.errors:
                reason_counts[error.reason] = reason_counts.get(error.reason, 0) + 1
            log.warning(
                f"DataSet 批量读取未完整成功: ref={dataset_ref}, values={len(result.member_values)}, "
                f"errors={len(result.errors)}, reasons={reason_counts}"
            )
        return self._read_dataset_values_by_members(dataset_ref) if allow_member_fallback else {}

    def _read_dataset_values_by_members(self, dataset_ref: str) -> dict[str, Any]:
        """仅在原生 DataSet 请求失败时使用的逐成员兼容回退。"""
        members = self.browse_dataset_directory(dataset_ref)
        if not members or not self._connection:
            return {}
        values: dict[str, Any] = {}
        with self._connection.native_operation() as conn:
            if conn is None:
                return values
            for member in members:
                ref = str(member.get("ref", "") or "")
                if not ref:
                    continue
                fc = str(member.get("fc", "") or infer_fc_from_address(ref) or "MX")
                iec_type = str(member.get("iec_type", "") or infer_iec_type_from_address(ref) or IEC_TYPE_UNKNOWN)
                mms_value = None
                try:
                    result = iec61850.IedConnection_readObject(
                        conn,
                        self._connection.build_dataset_ref(normalize_point_ref(ref)),
                        self._connection.get_fc_value(fc),
                    )
                    mms_value = result[0] if isinstance(result, (list, tuple)) else result
                    error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0
                    if error == iec61850.IED_ERROR_OK and mms_value is not None:
                        value = mms_value_to_python(mms_value, iec_type)
                        if value is not None:
                            values[ref] = value
                except Exception as exc:
                    log.debug(f"Read DataSet member failed: ref={ref}, error={exc}")
                finally:
                    if mms_value is not None:
                        with contextlib.suppress(Exception):
                            iec61850.MmsValue_delete(mms_value)
        return values


__all__ = [
    "DataSetsPlugin",
    "DatasetCatalog",
    "DatasetReadPlanner",
    "normalize_dataset_ref",
    "normalize_point_ref",
]
