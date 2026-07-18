"""IEC 61850 readers dispatched by native MMS type."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from ..defs.address import infer_fc_from_address, infer_iec_type_from_address
from ..defs.constants import HAS_IEC61850
from ..defs.mms_types import (
    MmsType,
    iec_type_from_mms_type,
    mms_type_from_iec_type,
    mms_type_from_native,
)
from ..log import log
from .native_calls import call_gil_safe

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class DatasetBatchReader(Protocol):
    """DataSets 插件实现的结构化批读接口。"""

    def read_points_batch(
        self,
        addresses: Sequence[str],
        fc_map: Mapping[str, str] | None,
        fallback,
        progress: Callable[[str, int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """批量读取一组测点；优先利用数据集读取能力，失败项再交给单点读取兜底。"""
        ...


def _delete_mms_value(value) -> None:
    """释放读取操作产生的 MmsValue，避免底层对象泄漏。"""
    if value is None:
        return
    try:
        iec61850.MmsValue_delete(value)
    except Exception as e:
        log.debug(f"释放读取 MmsValue 异常: {e}")


def _read_object_typed(conn, ref: str, fc_val) -> tuple[Any, MmsType]:
    """只调用一次 readObject，并依据返回的实际 MMS 类型转换结果。"""
    raw_value = None
    try:
        result = call_gil_safe(iec61850, "IedConnection_readObject", conn, ref, fc_val)
        if isinstance(result, (list, tuple)):
            raw_value = result[0] if result else None
            error = result[1] if len(result) > 1 else 0
        else:
            raw_value = result
            error = 0
        if error != iec61850.IED_ERROR_OK or raw_value is None:
            return None, MmsType.UNKNOWN
        actual_type = mms_type_from_native(int(iec61850.MmsValue_getType(raw_value)), iec61850)
        if actual_type in (MmsType.UNKNOWN, MmsType.DATA_ACCESS_ERROR):
            return None, actual_type
        value = _convert_mms_object(raw_value, actual_type)
        return value, actual_type
    except Exception as e:
        log.debug(f"通用 MMS 读取失败: ref={ref}, error={e}")
        return None, MmsType.UNKNOWN
    finally:
        _delete_mms_value(raw_value)


def _convert_mms_object(value, mms_type: MmsType) -> Any:
    """按 MmsValue 的实际类型转换标量、数组或结构体，不再发起额外网络读取。"""
    if mms_type is MmsType.BOOLEAN:
        return bool(iec61850.MmsValue_getBoolean(value))
    if mms_type is MmsType.BIT_STRING:
        return int(iec61850.MmsValue_getBitStringAsInteger(value))
    if mms_type is MmsType.INTEGER:
        return int(iec61850.MmsValue_toInt32(value))
    if mms_type is MmsType.UNSIGNED:
        return int(iec61850.MmsValue_toUint32(value))
    if mms_type is MmsType.FLOAT:
        return float(iec61850.MmsValue_toFloat(value))
    if mms_type is MmsType.UTC_TIME:
        return int(iec61850.MmsValue_getUtcTimeInMs(value))
    if mms_type is MmsType.BINARY_TIME:
        return int(iec61850.MmsValue_getBinaryTimeAsUtcMs(value))
    if mms_type is MmsType.OCTET_STRING:
        size = int(iec61850.MmsValue_getOctetStringSize(value))
        return bytes(int(iec61850.MmsValue_getOctetStringOctet(value, index)) for index in range(size)).hex()
    if mms_type in (MmsType.VISIBLE_STRING, MmsType.STRING, MmsType.GENERALIZED_TIME, MmsType.OBJ_ID):
        return str(iec61850.MmsValue_toString(value) or "")
    if mms_type is MmsType.BCD:
        return int(iec61850.MmsValue_toInt32(value))
    if mms_type in (MmsType.ARRAY, MmsType.STRUCTURE):
        size = int(iec61850.MmsValue_getArraySize(value))
        result = []
        for index in range(size):
            child = iec61850.MmsValue_getElement(value, index)
            child_type = mms_type_from_native(int(iec61850.MmsValue_getType(child)), iec61850)
            result.append(_convert_mms_object(child, child_type))
        return result
    return None


class FloatReader:
    def read(self, conn, ref: str, fc_val) -> Any:
        """使用浮点值读取器读取指定对象值，并转换为对应的 Python 类型。"""
        try:
            value, error = iec61850.IedConnection_readFloatValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return float(value)
            log.debug(f"读取浮点值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取浮点值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        """使用当前类型策略批量读取测点，并将成功值写入调用方提供的结果映射。"""
        _read_batch_with_strategy(self, conn, items, results)


class BooleanReader:
    def read(self, conn, ref: str, fc_val) -> Any:
        """使用布尔值读取器读取指定对象值，并转换为对应的 Python 类型。"""
        try:
            value, error = iec61850.IedConnection_readBooleanValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return bool(value)
            log.debug(f"读取布尔值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取布尔值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        """使用当前类型策略批量读取测点，并将成功值写入调用方提供的结果映射。"""
        _read_batch_with_strategy(self, conn, items, results)


class ObjectTypeReader:
    """Single-read MMS object strategy with runtime type validation."""

    def __init__(self, *accepted_types: MmsType):
        """记录当前读取策略允许接受的 MMS 运行时类型集合。"""
        self.accepted_types = frozenset(accepted_types)

    def read_typed(self, conn, ref: str, fc_val) -> tuple[Any, MmsType]:
        """读取一次对象值并返回实际 MMS 类型；类型不在允许集合中时丢弃该值。"""
        value, actual_type = _read_object_typed(conn, ref, fc_val)
        if self.accepted_types and actual_type not in self.accepted_types:
            if actual_type is not MmsType.DATA_ACCESS_ERROR:
                log.debug(
                    f"MMS 类型不匹配: ref={ref}, expected={[item.value for item in self.accepted_types]}, "
                    f"actual={actual_type.value}"
                )
            return None, actual_type
        return value, actual_type

    def read(self, conn, ref: str, fc_val) -> Any:
        """使用运行时类型读取器读取指定对象值，并转换为对应的 Python 类型。"""
        return self.read_typed(conn, ref, fc_val)[0]

    def read_batch(self, conn, items: list, results: dict) -> None:
        """使用当前类型策略批量读取测点，并将成功值写入调用方提供的结果映射。"""
        _read_batch_with_strategy(self, conn, items, results)


class IntegerReader(ObjectTypeReader):
    def __init__(self):
        """创建仅接受 MMS INTEGER 类型的读取策略。"""
        super().__init__(MmsType.INTEGER)


class UnsignedReader(ObjectTypeReader):
    def __init__(self):
        """创建仅接受 MMS UNSIGNED 类型的读取策略。"""
        super().__init__(MmsType.UNSIGNED)


class BitStringReader(ObjectTypeReader):
    def __init__(self):
        """创建仅接受 MMS BIT STRING 类型的读取策略。"""
        super().__init__(MmsType.BIT_STRING)


class StringReader(ObjectTypeReader):
    def __init__(self):
        """创建兼容可见字符串、普通字符串、八位组串和对象标识符的读取策略。"""
        super().__init__(MmsType.VISIBLE_STRING, MmsType.STRING, MmsType.OCTET_STRING, MmsType.OBJ_ID)


class TimestampReader(ObjectTypeReader):
    def __init__(self):
        """创建兼容 UTC Time、Binary Time 和 Generalized Time 的读取策略。"""
        super().__init__(MmsType.UTC_TIME, MmsType.BINARY_TIME, MmsType.GENERALIZED_TIME)


class AutoDetectReader(ObjectTypeReader):
    """Unknown-type strategy: exactly one readObject call, never a type cascade."""

    def __init__(self):
        """创建不限制预期类型、以服务端实际 MMS 类型为准的读取策略。"""
        super().__init__()


def _read_batch_with_strategy(strategy, conn, items: list, results: dict) -> None:
    """使用同一类型读取策略处理一批测点，仅把成功结果写入结果映射。"""
    for addr_str, ref, fc_val, _ in items:
        value = strategy.read(conn, ref, fc_val)
        if value is not None:
            results[addr_str] = value


READ_STRATEGIES = {
    MmsType.FLOAT: FloatReader(),
    MmsType.BOOLEAN: BooleanReader(),
    MmsType.INTEGER: IntegerReader(),
    MmsType.UNSIGNED: UnsignedReader(),
    MmsType.BIT_STRING: BitStringReader(),
    MmsType.VISIBLE_STRING: StringReader(),
    MmsType.STRING: StringReader(),
    MmsType.OCTET_STRING: StringReader(),
    MmsType.OBJ_ID: StringReader(),
    MmsType.UTC_TIME: TimestampReader(),
    MmsType.BINARY_TIME: TimestampReader(),
    MmsType.GENERALIZED_TIME: TimestampReader(),
    MmsType.BCD: ObjectTypeReader(MmsType.BCD),
    MmsType.ARRAY: ObjectTypeReader(MmsType.ARRAY),
    MmsType.STRUCTURE: ObjectTypeReader(MmsType.STRUCTURE),
    MmsType.DATA_ACCESS_ERROR: ObjectTypeReader(MmsType.DATA_ACCESS_ERROR),
    MmsType.UNKNOWN: AutoDetectReader(),
}


class Iec61850Reader:
    """Resolve FC/MMS metadata and execute a single type-specific read strategy."""

    def __init__(self, connection, registry=None, dataset_reader: DatasetBatchReader | None = None):
        """绑定连接、测点注册表和可选数据集读取器，供单点及批量读取复用。"""
        self._connection = connection
        self._registry = registry
        self._dataset_reader = dataset_reader

    def set_dataset_reader(self, dataset_reader: DatasetBatchReader | None) -> None:
        """插件初始化完成后注入 DataSet 读取引擎。"""
        self._dataset_reader = dataset_reader

    def read(self, address: str, fc: str = "", mms_type: str | MmsType = "") -> Any:
        """使用MMS 数据读取器读取指定对象值，并转换为对应的 Python 类型。"""
        if not self._connection.ensure_connected():
            return None

        addr_str = str(address)
        ref = self._build_ref(addr_str)
        fc_val = self._resolve_fc(addr_str, fc)
        try:
            resolved_mms_type = MmsType(mms_type) if mms_type else self._resolve_mms_type(addr_str)
        except (TypeError, ValueError):
            resolved_mms_type = self._resolve_mms_type(addr_str)

        value = self._read_once(addr_str, ref, fc_val, resolved_mms_type)
        if value is not None:
            return value
        if self._connection.reconnect_if_unhealthy(f"read {ref}"):
            return self._read_once(addr_str, ref, fc_val, resolved_mms_type)
        return None

    def _read_once(self, address: str, ref: str, fc_val, mms_type: MmsType) -> Any:
        """在当前底层连接上执行一次读取，不在本函数内部触发重连。"""
        strategy = READ_STRATEGIES.get(mms_type, READ_STRATEGIES[MmsType.UNKNOWN])
        with self._connection.native_operation() as conn:
            if conn is None:
                return None
            try:
                if mms_type is MmsType.UNKNOWN and isinstance(strategy, AutoDetectReader):
                    value, actual_type = strategy.read_typed(conn, ref, fc_val)
                    if actual_type not in (MmsType.UNKNOWN, MmsType.DATA_ACCESS_ERROR):
                        self._cache_runtime_type(address, actual_type)
                    return value
                return strategy.read(conn, ref, fc_val)
            except Exception as e:
                log.error(f"IEC61850 读取异常: address={address}, ref={ref}, error={e}")
                return None

    def read_batch(
        self,
        addresses: list[str],
        fc_map: dict[str, str] | None = None,
        progress: Callable[[str, int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """DataSet 优先批读；无目录或单个成员失败时仅回退对应测点。"""
        if not addresses:
            return {}

        if self._dataset_reader is not None:
            return self._dataset_reader.read_points_batch(
                addresses,
                fc_map,
                self._read_fallback_once,
                progress=progress,
            )

        if not self._connection.ensure_connected():
            return {}
        results = self._read_fallback_once(addresses, fc_map)
        if len(results) == len(addresses):
            return results
        if self._connection.reconnect_if_unhealthy(f"batch read {len(addresses)} points, got {len(results)} values"):
            missing = [address for address in addresses if address not in results]
            retry_results = self._read_fallback_once(missing, fc_map)
            results.update(retry_results)
        return results

    def _read_fallback_once(
        self,
        addresses: Sequence[str],
        fc_map: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """在同一个原生连接锁内，只读取未覆盖或批读失败的测点。"""
        results: dict[str, Any] = {}
        unique_addresses = tuple(dict.fromkeys(str(address) for address in addresses))
        with self._connection.native_operation() as conn:
            if conn is None:
                return results
            for addr_str in unique_addresses:
                ref = self._build_ref(addr_str)
                fc = fc_map.get(addr_str, "") if fc_map else ""
                fc_val = self._resolve_fc(addr_str, fc)
                mms_type = self._resolve_mms_type(addr_str)
                strategy = READ_STRATEGIES.get(mms_type, READ_STRATEGIES[MmsType.UNKNOWN])
                try:
                    if mms_type is MmsType.UNKNOWN and isinstance(strategy, AutoDetectReader):
                        value, actual_type = strategy.read_typed(conn, ref, fc_val)
                        if actual_type not in (MmsType.UNKNOWN, MmsType.DATA_ACCESS_ERROR):
                            self._cache_runtime_type(addr_str, actual_type)
                    else:
                        value = strategy.read(conn, ref, fc_val)
                    if value is not None:
                        results[addr_str] = value
                except Exception as e:
                    log.debug(f"IEC61850 fallback read failed: address={addr_str}, ref={ref}, error={e}")
        return results

    def _build_ref(self, address: str) -> str:
        """把项目测点地址转换为底层 IED 连接可识别的对象引用。"""
        if self._registry:
            ref = self._registry.get_ref(address)
            if ref:
                return ref
        from ..defs.address import is_full_ref, parse_ref

        if is_full_ref(address):
            parsed = parse_ref(address)
            if parsed:
                ld_inst = parsed[0]
                model_name = str(self._connection.model_name or "")
                discovered_lds = tuple(getattr(self._connection, "_discovered_lds", ()) or ())
                native_domain = (
                    ld_inst if ld_inst in discovered_lds or ld_inst.startswith(model_name) else f"{model_name}{ld_inst}"
                )
                return f"{native_domain}/{address.split('/', 1)[1]}"
        safe_addr = str(address).replace(".", "_").replace("/", "_").replace("\\", "_").replace("-", "_")
        mms_type = self._resolve_mms_type(address)
        if mms_type is MmsType.FLOAT:
            return f"{self._connection.model_name}{self._connection.ld_name}/MMXU1.MV_{safe_addr}.mag.f"
        return f"{self._connection.model_name}{self._connection.ld_name}/GGIO1.SPS_{safe_addr}.stVal"

    def _resolve_fc(self, address: str, fc: str = ""):
        """优先采用调用方或注册表中的功能约束，缺失时再根据地址推断。"""
        if not fc and self._registry:
            fc = self._registry.get_fc(address)
        if not fc:
            fc = infer_fc_from_address(address)
        return self._connection.get_fc_value(fc)

    def _resolve_mms_type(self, address: str) -> MmsType:
        """优先使用注册表已知类型，缺失时根据标准数据属性路径推断 MMS 类型。"""
        if self._registry:
            get_mms_type = getattr(self._registry, "get_mms_type", None)
            raw_type = get_mms_type(address) if callable(get_mms_type) else ""
            try:
                return MmsType(raw_type)
            except (TypeError, ValueError):
                legacy_type = self._registry.get_iec_type(address)
                if legacy_type:
                    return mms_type_from_iec_type(legacy_type)
        return mms_type_from_iec_type(infer_iec_type_from_address(address))

    def _cache_runtime_type(self, address: str, mms_type: MmsType) -> None:
        """把在线读取确认的 MMS 类型写回测点注册表，供后续读取直接选择正确策略。"""
        if not self._registry:
            return
        set_mms_type = getattr(self._registry, "set_mms_type", None)
        if callable(set_mms_type):
            set_mms_type(address, mms_type.value)
        self._registry.set_iec_type(address, iec_type_from_mms_type(mms_type).value)
