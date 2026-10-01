"""Validate JSON values and convert them at the SDK boundary."""

import base64
from datetime import UTC, datetime
import math
from typing import Any

INTEGER_RANGES = {
    "SByte": (-128, 127),
    "Byte": (0, 255),
    "Int16": (-(2**15), 2**15 - 1),
    "UInt16": (0, 2**16 - 1),
    "Int32": (-(2**31), 2**31 - 1),
    "UInt32": (0, 2**32 - 1),
    "Int64": (-(2**63), 2**63 - 1),
    "UInt64": (0, 2**64 - 1),
}
VALUE_TYPES = ("Boolean", *INTEGER_RANGES, "Float", "Double", "String", "DateTime", "ByteString")


def validate_value(data_type: str, value: Any, value_rank: int = -1) -> Any:
    if value_rank == 1:
        if not isinstance(value, list) or len(value) > 512:
            raise ValueError("一维数组必须为最多 512 项的 JSON 数组")
        return [validate_value(data_type, item) for item in value]
    if value_rank != -1:
        raise ValueError("目前仅支持标量或一维数组")
    if data_type == "Boolean":
        if not isinstance(value, bool):
            raise ValueError("节点要求 Boolean 值")
    elif data_type in INTEGER_RANGES:
        if data_type in {"Int64", "UInt64"} and isinstance(value, dict) and set(value) == {"integer"}:
            try:
                value = int(value["integer"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"节点要求 {data_type} 整数") from exc
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"节点要求 {data_type} 整数")
        lower, upper = INTEGER_RANGES[data_type]
        if not lower <= value <= upper:
            raise ValueError(f"写入值超出 {data_type} 范围")
    elif data_type in {"Float", "Double"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"节点要求 {data_type} 数值")
        try:
            value = float(value)
        except OverflowError as exc:
            raise ValueError("写入值超出浮点数范围") from exc
        if not math.isfinite(value):
            raise ValueError("写入值必须是有限数值")
        if data_type == "Float" and abs(value) > 3.4028234663852886e38:
            raise ValueError("写入值超出 Float 范围")
    elif data_type == "String":
        if not isinstance(value, str) or len(value) > 65536:
            raise ValueError("String 必须为最多 65536 字符的字符串")
    elif data_type == "DateTime":
        if not isinstance(value, str):
            raise ValueError("DateTime 必须为带时区的 ISO 8601 字符串")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("DateTime 格式无效") from exc
        if parsed.tzinfo is None:
            raise ValueError("DateTime 必须包含时区")
        value = parsed.astimezone(UTC).isoformat()
    elif data_type == "ByteString":
        if not isinstance(value, dict) or set(value) != {"base64"}:
            raise ValueError('ByteString 必须为 {"base64": "..."}')
        if not isinstance(value["base64"], str) or len(value["base64"]) > 87384:
            raise ValueError("ByteString 超过 64 KB")
        try:
            binary = base64.b64decode(value["base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("ByteString base64 无效") from exc
        if len(binary) > 65536:
            raise ValueError("ByteString 超过 64 KB")
    else:
        raise ValueError(f"不支持的数据类型: {data_type}")
    return value


def sdk_value(data_type: str, value: Any, value_rank: int = -1) -> Any:
    value = validate_value(data_type, value, value_rank)
    if value_rank == 1:
        return [sdk_value(data_type, item) for item in value]
    if data_type == "DateTime":
        return datetime.fromisoformat(value)
    if data_type == "ByteString":
        return base64.b64decode(value["base64"])
    return value
