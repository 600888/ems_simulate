"""Point/ASDU helpers shared by IEC 101 and IEC 104 handlers."""

from __future__ import annotations

from typing import Any

from src.enums.modbus_register import Decode
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint
from src.enums.points.iec104_type import (
    IEC104_TYPE_REGISTRY,
    IEC104Type,
    decode_iec104_value,
    resolve_iec104_type,
)


def resolve_asdu_type(point: BasePoint) -> IEC104Type:
    return resolve_iec104_type(point.iec_type_id, point.frame_type)


def resolve_asdu_type_code(point: BasePoint) -> int:
    return IEC104_TYPE_REGISTRY[resolve_asdu_type(point)].type_code


def decode_point_value(point: BasePoint, value: Any) -> Any:
    """Convert a decoded IEC 60870 value to the point's protocol-raw value."""
    if isinstance(point, (Yx, Yk)):
        return int(bool(value)) if resolve_asdu_type_code(point) not in (3, 4, 31, 46, 59) else int(value)
    if isinstance(point, (Yc, Yt)):
        decoded = decode_iec104_value(value, point.iec_type_id)
        return float(decoded) if Decode.get_info(point.decode).is_float else int(round(decoded))
    return value
