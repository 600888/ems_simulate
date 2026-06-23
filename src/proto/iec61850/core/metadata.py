"""MetadataReader — 品质(q)与时标(t)按需读取服务

使用 IedConnection_readObject 读取 MMS PACKED_LIST / UTC_TIME 结构体:
- q → readObject → Quality_fromMmsValue → 解码 validity/source/test/operatorBlocked
- t → readObject → Timestamp_create → Timestamp_fromMmsValue → 解码秒/分秒/闰秒等

BAMS 等设备不暴露 q/t 子属性 (.q.validity, .t.seconds),
只能用 readObject 读完整结构体。失败时静默返回 empty()。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..defs.constants import HAS_IEC61850
from ..log import log

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
        return self.validity is not None and self.validity == 0 and self.source != 1 and self.test is not True

    @property
    def is_readable(self) -> bool:
        return self.raw_packed is not None or self.validity is not None

    def to_dict(self) -> dict[str, int | bool | None]:
        return {
            "validity": self.validity,
            "detailQuality": self.detail_quality,
            "source": self.source,
            "operatorBlocked": self.operator_blocked,
            "test": self.test,
        }

    @classmethod
    def empty(cls) -> QualityInfo:
        return cls()


@dataclass(slots=True, frozen=True)
class TimestampInfo:
    """时标 (EntryTime) 结构体 — 由 Unix 毫秒解码

    通过 readTimestampValue 读取完整 EntryTime 后解码得到。
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
        return self.unix_timestamp_ms is not None or self.seconds is not None

    def to_dict(self) -> dict[str, int | bool | None]:
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
        return cls()


@dataclass(slots=True, frozen=True)
class MetadataInfo:
    """DO 完整元数据 (品质 + 时标)"""

    quality: QualityInfo = field(default_factory=QualityInfo.empty)
    timestamp: TimestampInfo = field(default_factory=TimestampInfo.empty)

    @property
    def is_readable(self) -> bool:
        return self.quality.is_readable or self.timestamp.is_readable

    def to_dict(self) -> dict:
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

    def read_quality(
        self,
        connection: Iec61850Connection,
        do_ref: str,
        *,
        fc: str = "",
    ) -> QualityInfo:
        """读取 DO 的品质 (q) — IedConnection_readQualityValue 专用 API"""
        if not connection or not connection.is_connected:
            return QualityInfo.empty()
        conn = connection.connection
        if conn is None:
            return QualityInfo.empty()
        fc_val = connection.get_fc_value(fc or self.DEFAULT_FC)
        ref = f"{do_ref}.q"

        try:
            result = iec61850.IedConnection_readObject(conn, ref, fc_val)
            mms_value = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0

            if error == iec61850.IED_ERROR_OK and mms_value:
                packed = int(iec61850.MmsValue_getBitStringAsInteger(mms_value))
                return QualityInfo.from_packed(packed)
            else:
                log.debug(f"readObject (quality) 失败: {do_ref}, error={error}")
        except Exception as e:
            log.debug(f"readObject (quality) 异常: {do_ref}, {e}")

        return QualityInfo.empty()

    def read_timestamp(
        self,
        connection: Iec61850Connection,
        do_ref: str,
        *,
        fc: str = "",
    ) -> TimestampInfo:
        """读取 DO 的时标 (t) — IedConnection_readObject + MmsValue_getUtcTimeInMs"""
        if not connection or not connection.is_connected:
            return TimestampInfo.empty()
        conn = connection.connection
        if conn is None:
            return TimestampInfo.empty()
        fc_val = connection.get_fc_value(fc or self.DEFAULT_FC)
        ref = f"{do_ref}.t"

        try:
            result = iec61850.IedConnection_readObject(conn, ref, fc_val)
            mms_value = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0

            if error != iec61850.IED_ERROR_OK or not mms_value:
                return TimestampInfo.empty()

            ms = int(iec61850.MmsValue_getUtcTimeInMs(mms_value))
            return TimestampInfo(
                seconds=ms // 1000,
                fraction=int((ms % 1000) * (1 << 24) / 1000),
                unix_timestamp_ms=ms,
            )
        except Exception:
            return TimestampInfo.empty()

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
        q_info = self.read_quality(connection, do_ref, fc=fc)
        t_info = self.read_timestamp(connection, do_ref, fc=fc)
        return MetadataInfo(quality=q_info, timestamp=t_info)


# ============================================================
# 模块级便捷函数
# ============================================================

_default_reader = MetadataReader()


def read_quality(conn: Iec61850Connection, do_ref: str, *, fc: str = "") -> QualityInfo:
    """读取品质: 先读完整 q 结构体(Packed 整数解码), 失败降级子属性"""
    return _default_reader.read_quality(conn, do_ref, fc=fc)


def read_timestamp(conn: Iec61850Connection, do_ref: str, *, fc: str = "") -> TimestampInfo:
    """读取时标: 先读完整 t 结构体(readTimestampValue), 失败降级子属性"""
    return _default_reader.read_timestamp(conn, do_ref, fc=fc)


def read_metadata(conn: Iec61850Connection, do_ref: str, *, fc: str = "") -> MetadataInfo:
    """读取完整元数据"""
    return _default_reader.read_metadata(conn, do_ref, fc=fc)
