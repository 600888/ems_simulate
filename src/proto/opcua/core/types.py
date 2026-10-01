"""JSON-safe OPC UA value contracts, independent of the HTTP layer."""

from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any

from asyncua import ua


def _json_value(value: Any, budget: list[int] | None = None, depth: int = 0) -> Any:
    if budget is None:
        budget = [1000]
    budget[0] -= 1
    if budget[0] < 0 or depth > 4:
        raise ValueError("OPC UA 值超过 JSON 编码大小或深度上限")
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("OPC UA 非有限数值不能编码为 JSON")
        return value
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat()
    if isinstance(value, bytes):
        import base64

        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (tuple, list)):
        return [_json_value(item, budget, depth + 1) for item in value]
    # Structures need an explicit schema before they can be edited in the UI.
    raise ValueError(f"暂不支持 JSON 编码的 OPC UA 值类型: {type(value).__name__}")


def value_snapshot(node_id: str, data_value: ua.DataValue) -> dict[str, Any]:
    variant = data_value.Value
    return {
        "node_id": node_id,
        "value": _json_value(variant.Value if variant else None),
        "variant_type": variant.VariantType.name if variant else None,
        "status_code": data_value.StatusCode.name,
        "source_timestamp": _json_value(data_value.SourceTimestamp),
        "server_timestamp": _json_value(data_value.ServerTimestamp),
    }
