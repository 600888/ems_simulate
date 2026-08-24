"""MetadataReader — 品质(q)与时标(t)按需读取服务

使用 IedConnection_readObject 读取 MMS BIT STRING / UTC TIME:
- q → 类型检查 → 位串解码 validity/source/test/operatorBlocked
- t → 类型检查 → UTC 毫秒时间戳解码

BAMS 等设备不暴露 q/t 子属性 (.q.validity, .t.seconds),
只能用 readObject 读完整结构体。失败时静默返回 empty()。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..defs.constants import HAS_IEC61850
from ..defs.error_codes import format_ied_error
from ..log import log
from .native_calls import call_gil_safe

if TYPE_CHECKING:
    from .connection import Iec61850Connection

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


# ============================================================
# 产出类型 — 不可变 dataclass
# ============================================================


@dataclass(slots=True, frozen=True)
class QualityInfo:
    """品质 (Quality) 结构体 — IEC 61850-7-2 PACKED LIST 解码

    ┌─────────────┬──────┬──────────────────────────┐
    │ 字段        │ 位域 │ 含义                     │
    ├─────────────┼──────┼──────────────────────────┤
    │ validity    │ 0-1  │ 0=good,1=invalid,2=questionable,3=overflow │
    │ detailQual  │ 2-9  │ 详细品质码 (8 bit)       │
    │ source      │ 10   │ 0=process, 1=substituted │
    │ test        │ 11   │ 0=normal, 1=test         │
    │ opBlocked   │ 12   │ 0=normal, 1=blocked      │
    └─────────────┴──────┴──────────────────────────┘
    """

    validity: int | None = None
    detail_quality: int | None = None
    source: int | None = None
    operator_blocked: bool | None = None
    test: bool | None = None
    raw_packed: int | None = field(default=None, repr=False)

    @classmethod
    def from_packed(cls, raw: int) -> QualityInfo:
        """从原始打包整数解码 Quality"""
        return cls(
            validity=raw & 0x3,
            detail_quality=(raw >> 2) & 0xFF,
            source=(raw >> 10) & 0x1,
            test=bool((raw >> 11) & 0x1),
            operator_blocked=bool((raw >> 12) & 0x1),
            raw_packed=raw,
        )

    @property
    def is_valid(self) -> bool:
        """判断QualityInfo是否处于有效状态。"""
        return self.validity is not None and self.validity == 0 and self.source != 1 and self.test is not True

    @property
    def is_readable(self) -> bool:
        """判断QualityInfo是否处于可读状态。"""
        return self.raw_packed is not None or self.validity is not None

    def to_dict(self) -> dict[str, int | bool | None]:
        """把QualityInfo转换为可序列化字典。"""
        return {
            "validity": self.validity,
            "detailQuality": self.detail_quality,
            "source": self.source,
            "operatorBlocked": self.operator_blocked,
            "test": self.test,
        }

    @classmethod
    def empty(cls) -> QualityInfo:
        """返回字段均处于未知状态的空元数据对象，用于读取失败时保持返回结构稳定。"""
        return cls()


@dataclass(slots=True, frozen=True)
class TimestampInfo:
    """时标 (EntryTime) 结构体 — 由 Unix 毫秒解码

    通过 readObject 读取完整 UTC TIME 后解码得到。
    """

    seconds: int | None = None
    fraction: int | None = None
    time_accuracy: int | None = None
    leap_seconds_known: bool | None = None
    clock_failure: bool | None = None
    clock_not_synchronized: bool | None = None
    unix_timestamp_ms: int | None = field(default=None, repr=False)

    @classmethod
    def from_unix_ms(cls, ms: int) -> TimestampInfo:
        """从 Unix 毫秒时间戳构建"""
        return cls(
            seconds=ms // 1000,
            fraction=int((ms % 1000) * (1 << 24) / 1000),
            unix_timestamp_ms=ms,
        )

    @property
    def is_readable(self) -> bool:
        """判断TimestampInfo是否处于可读状态。"""
        return self.unix_timestamp_ms is not None or self.seconds is not None

    def to_dict(self) -> dict[str, int | bool | None]:
        """把TimestampInfo转换为可序列化字典。"""
        return {
            "seconds": self.seconds,
            "fraction": self.fraction,
            "timeAccuracy": self.time_accuracy,
            "leapSecondsKnown": self.leap_seconds_known,
            "clockFailure": self.clock_failure,
            "clockNotSynchronized": self.clock_not_synchronized,
            "unixTimestampMs": self.unix_timestamp_ms,
        }

    @classmethod
    def empty(cls) -> TimestampInfo:
        """返回字段均处于未知状态的空元数据对象，用于读取失败时保持返回结构稳定。"""
        return cls()


@dataclass(slots=True, frozen=True)
class MetadataInfo:
    """DO 完整元数据 (品质 + 时标)"""

    quality: QualityInfo = field(default_factory=QualityInfo.empty)
    timestamp: TimestampInfo = field(default_factory=TimestampInfo.empty)

    @property
    def is_readable(self) -> bool:
        """判断MetadataInfo是否处于可读状态。"""
        return self.quality.is_readable or self.timestamp.is_readable

    def to_dict(self) -> dict:
        """把MetadataInfo转换为可序列化字典。"""
        return {
            "quality": self.quality.to_dict(),
            "timestamp": self.timestamp.to_dict(),
        }


# ============================================================
# MetadataReader — 按需读取服务
# ============================================================


class MetadataReader:
    """品质与时标按需读取服务

    不依赖 PointRegistry，直接通过 IedConnection + MMS 引用读取。
    """

    # 默认 FC (q 和 t 通常为 MX; ST 类型 DO 的 q/t 为 ST)
    DEFAULT_FC = "MX"
    _DATA_ACCESS_ERROR_NAMES = {
        -2: "no-response",
        -1: "success",
        0: "object-invalidated",
        1: "hardware-fault",
        2: "temporarily-unavailable",
        3: "object-access-denied",
        4: "object-undefined",
        5: "invalid-address",
        6: "type-unsupported",
        7: "type-inconsistent",
        8: "object-attribute-inconsistent",
        9: "object-access-unsupported",
        10: "object-none-existent",
        11: "object-value-invalid",
        12: "unknown",
    }

    def read_quality(
        self,
        connection: Iec61850Connection,
        do_ref: str,
        *,
        fc: str = "",
    ) -> QualityInfo:
        """读取 DO 的品质 (q)，仅对 MMS BIT STRING 执行解码。"""
        if not connection or not connection.is_connected:
            return QualityInfo.empty()
        ref = f"{do_ref}.q"

        with connection.native_operation() as conn:
            if conn is None:
                return QualityInfo.empty()
            for fc_name in self._fc_candidates(fc):
                mms_value = None
                try:
                    fc_val = connection.get_fc_value(fc_name)
                    result = call_gil_safe(iec61850, "IedConnection_readObject", conn, ref, fc_val)
                    mms_value = result[0] if isinstance(result, (list, tuple)) else result
                    error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0

                    if error != iec61850.IED_ERROR_OK or not mms_value:
                        log.debug(
                            f"readObject (quality) 失败: ref={ref}, fc={fc_name}, error={format_ied_error(error)}"
                        )
                        continue

                    value_type = iec61850.MmsValue_getType(mms_value)
                    if self._log_data_access_error("品质", ref, fc_name, mms_value, value_type):
                        continue
                    if value_type != getattr(iec61850, "MMS_BIT_STRING", None):
                        log.debug(f"品质 MMS 类型不匹配: ref={ref}, fc={fc_name}, type={value_type}")
                        continue

                    packed = int(iec61850.MmsValue_getBitStringAsInteger(mms_value))
                    return QualityInfo.from_packed(packed)
                except Exception as e:
                    log.debug(f"readObject (quality) 异常: ref={ref}, fc={fc_name}, error={e}")
                finally:
                    self._delete_mms_value(mms_value)

        return QualityInfo.empty()

    def read_timestamp(
        self,
        connection: Iec61850Connection,
        do_ref: str,
        *,
        fc: str = "",
    ) -> TimestampInfo:
        """读取 DO 的时标 (t)，仅对 MMS UTC TIME 执行解码。"""
        if not connection or not connection.is_connected:
            return TimestampInfo.empty()
        ref = f"{do_ref}.t"

        with connection.native_operation() as conn:
            if conn is None:
                return TimestampInfo.empty()
            for fc_name in self._fc_candidates(fc):
                mms_value = None
                try:
                    fc_val = connection.get_fc_value(fc_name)
                    # 使用线程安全的 IedConnection_readObject 方法
                    result = call_gil_safe(iec61850, "IedConnection_readObject", conn, ref, fc_val)
                    mms_value = result[0] if isinstance(result, (list, tuple)) else result
                    error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0

                    if error != iec61850.IED_ERROR_OK or not mms_value:
                        log.debug(
                            f"readObject (timestamp) 失败: ref={ref}, fc={fc_name}, error={format_ied_error(error)}"
                        )
                        continue

                    value_type = iec61850.MmsValue_getType(mms_value)
                    if self._log_data_access_error("时标", ref, fc_name, mms_value, value_type):
                        continue
                    if value_type != getattr(iec61850, "MMS_UTC_TIME", None):
                        log.debug(f"时标 MMS 类型不匹配: ref={ref}, fc={fc_name}, type={value_type}")
                        continue

                    ms = int(iec61850.MmsValue_getUtcTimeInMs(mms_value))
                    return TimestampInfo.from_unix_ms(ms)
                except Exception as e:
                    log.debug(f"readObject (timestamp) 异常: ref={ref}, fc={fc_name}, error={e}")
                finally:
                    self._delete_mms_value(mms_value)

        return TimestampInfo.empty()

    def _fc_candidates(self, fc: str) -> tuple[str, ...]:
        """生成元数据读取可尝试的功能约束顺序，并优先使用测点已登记的功能约束。"""
        primary = (fc or self.DEFAULT_FC).upper()
        if primary == "MX":
            return ("MX", "ST")
        if primary == "ST":
            return ("ST", "MX")
        return (primary,)

    def _log_data_access_error(self, label: str, ref: str, fc: str, mms_value, value_type: int) -> bool:
        """按对象引用和功能约束记录一次数据访问错误，避免重复日志刷屏。"""
        if value_type != getattr(iec61850, "MMS_DATA_ACCESS_ERROR", 15):
            return False
        error_code = None
        getter = getattr(iec61850, "MmsValue_getDataAccessError", None)
        if getter is not None:
            try:
                error_code = int(getter(mms_value))
            except Exception:
                pass
        error_name = self._DATA_ACCESS_ERROR_NAMES.get(error_code, "unavailable")
        log.debug(f"{label} MMS 访问失败: ref={ref}, fc={fc}, access_error={error_code}({error_name})")
        return True

    @staticmethod
    def _delete_mms_value(mms_value) -> None:
        """释放读取操作产生的 MmsValue，避免底层对象泄漏。"""
        if mms_value is None:
            return
        try:
            iec61850.MmsValue_delete(mms_value)
        except Exception as e:
            log.debug(f"释放元数据 MmsValue 异常: {e}")

    def read_metadata(
        self,
        connection: Iec61850Connection,
        do_ref: str,
        *,
        fc: str = "",
    ) -> MetadataInfo:
        """读取 DO 的完整元数据 (品质 + 时标)"""
        if not connection or not connection.ensure_connected():
            return MetadataInfo()

        info = self._read_metadata_once(connection, do_ref, fc=fc)
        if info.is_readable:
            return info

        if connection.reconnect_if_unhealthy(f"read metadata {do_ref}"):
            return self._read_metadata_once(connection, do_ref, fc=fc)
        return info

    def _read_metadata_once(
        self,
        connection: Iec61850Connection,
        do_ref: str,
        *,
        fc: str = "",
    ) -> MetadataInfo:
        """使用指定功能约束读取一次品质或时标元数据，并返回解析结果与错误码。"""
        q_info = self.read_quality(connection, do_ref, fc=fc)
        t_info = self.read_timestamp(connection, do_ref, fc=fc)
        return MetadataInfo(quality=q_info, timestamp=t_info)


# ============================================================
# 模块级便捷函数
# ============================================================

_default_reader = MetadataReader()


def read_quality(conn: Iec61850Connection, do_ref: str, *, fc: str = "") -> QualityInfo:
    """读取品质：读取完整 q 位串，类型不匹配时返回空结果。"""
    return _default_reader.read_quality(conn, do_ref, fc=fc)


def read_timestamp(conn: Iec61850Connection, do_ref: str, *, fc: str = "") -> TimestampInfo:
    """读取时标：读取完整 t UTC TIME，类型不匹配时返回空结果。"""
    return _default_reader.read_timestamp(conn, do_ref, fc=fc)


def read_metadata(conn: Iec61850Connection, do_ref: str, *, fc: str = "") -> MetadataInfo:
    """读取完整元数据"""
    return _default_reader.read_metadata(conn, do_ref, fc=fc)
