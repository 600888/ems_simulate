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
    ) -> dict[str, Any]: ...


def _delete_mms_value(value) -> None:
    if value is None:
        return
    try:
        iec61850.MmsValue_delete(value)
    except Exception as e:
        log.debug(f"释放读取 MmsValue 异常: {e}")


def _read_object_typed(conn, ref: str, fc_val) -> tuple[Any, MmsType]:
    """Read once with readObject and convert according to the returned MMS type."""
    raw_value = None
    try:
        result = iec61850.IedConnection_readObject(conn, ref, fc_val)
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
    """Convert one already-read MmsValue using its exact runtime type."""
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
        try:
            value, error = iec61850.IedConnection_readFloatValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return float(value)
            log.debug(f"读取浮点值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取浮点值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        _read_batch_with_strategy(self, conn, items, results)


class BooleanReader:
    def read(self, conn, ref: str, fc_val) -> Any:
        try:
            value, error = iec61850.IedConnection_readBooleanValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return bool(value)
            log.debug(f"读取布尔值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取布尔值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        _read_batch_with_strategy(self, conn, items, results)


class ObjectTypeReader:
    """Single-read MMS object strategy with runtime type validation."""

    def __init__(self, *accepted_types: MmsType):
        self.accepted_types = frozenset(accepted_types)

    def read_typed(self, conn, ref: str, fc_val) -> tuple[Any, MmsType]:
        value, actual_type = _read_object_typed(conn, ref, fc_val)
        if self.accepted_types and actual_type not in self.accepted_types:
            log.debug(
                f"MMS 类型不匹配: ref={ref}, expected={[item.value for item in self.accepted_types]}, "
                f"actual={actual_type.value}"
            )
            return None, actual_type
        return value, actual_type

    def read(self, conn, ref: str, fc_val) -> Any:
        return self.read_typed(conn, ref, fc_val)[0]

    def read_batch(self, conn, items: list, results: dict) -> None:
        _read_batch_with_strategy(self, conn, items, results)


class IntegerReader(ObjectTypeReader):
    def __init__(self):
        super().__init__(MmsType.INTEGER)


class UnsignedReader(ObjectTypeReader):
    def __init__(self):
        super().__init__(MmsType.UNSIGNED)


class BitStringReader(ObjectTypeReader):
    def __init__(self):
        super().__init__(MmsType.BIT_STRING)


class StringReader(ObjectTypeReader):
    def __init__(self):
        super().__init__(MmsType.VISIBLE_STRING, MmsType.STRING, MmsType.OCTET_STRING, MmsType.OBJ_ID)


class TimestampReader(ObjectTypeReader):
    def __init__(self):
        super().__init__(MmsType.UTC_TIME, MmsType.BINARY_TIME, MmsType.GENERALIZED_TIME)


class AutoDetectReader(ObjectTypeReader):
    """Unknown-type strategy: exactly one readObject call, never a type cascade."""

    def __init__(self):
        super().__init__()


def _read_batch_with_strategy(strategy, conn, items: list, results: dict) -> None:
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
        self._connection = connection
        self._registry = registry
        self._dataset_reader = dataset_reader

    def set_dataset_reader(self, dataset_reader: DatasetBatchReader | None) -> None:
        """插件初始化完成后注入 DataSet 读取引擎。"""
        self._dataset_reader = dataset_reader

    def read(self, address: str, fc: str = "") -> Any:
        if not self._connection.ensure_connected():
            return None

        addr_str = str(address)
        ref = self._build_ref(addr_str)
        fc_val = self._resolve_fc(addr_str, fc)
        mms_type = self._resolve_mms_type(addr_str)

        value = self._read_once(addr_str, ref, fc_val, mms_type)
        if value is not None:
            return value
        if self._connection.reconnect_if_unhealthy(f"read {ref}"):
            return self._read_once(addr_str, ref, fc_val, mms_type)
        return None

    def _read_once(self, address: str, ref: str, fc_val, mms_type: MmsType) -> Any:
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
        if self._registry:
            ref = self._registry.get_ref(address)
            if ref:
                return ref
        from ..defs.address import is_full_ref, parse_ref

        if is_full_ref(address):
            parsed = parse_ref(address)
            if parsed:
                return f"{self._connection.model_name}{parsed[0]}/{address.split('/', 1)[1]}"
        safe_addr = str(address).replace(".", "_").replace("/", "_").replace("\\", "_").replace("-", "_")
        mms_type = self._resolve_mms_type(address)
        if mms_type is MmsType.FLOAT:
            return f"{self._connection.model_name}{self._connection.ld_name}/MMXU1.MV_{safe_addr}.mag.f"
        return f"{self._connection.model_name}{self._connection.ld_name}/GGIO1.SPS_{safe_addr}.stVal"

    def _resolve_fc(self, address: str, fc: str = ""):
        if not fc and self._registry:
            fc = self._registry.get_fc(address)
        if not fc:
            fc = infer_fc_from_address(address)
        return self._connection.get_fc_value(fc)

    def _resolve_mms_type(self, address: str) -> MmsType:
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
        if not self._registry:
            return
        set_mms_type = getattr(self._registry, "set_mms_type", None)
        if callable(set_mms_type):
            set_mms_type(address, mms_type.value)
        self._registry.set_iec_type(address, iec_type_from_mms_type(mms_type).value)
