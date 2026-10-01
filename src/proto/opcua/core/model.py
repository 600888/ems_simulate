"""Plain Python validation for the M1 scalar variable model."""

from typing import Any

from src.proto.opcua.core.values import validate_value


def validate_variable(data: dict[str, Any]) -> dict[str, Any]:
    node_id = str(data["node_id"])
    if len(node_id) > 512 or not node_id.startswith("ns=2;s=") or not node_id[7:]:
        raise ValueError("M1 节点 ID 必须是最多 512 字符的 ns=2;s=... 字符串标识")
    browse_name = str(data["browse_name"]).strip()
    if not browse_name or len(browse_name) > 255:
        raise ValueError("BrowseName 必须在 1 到 255 个字符之间")
    data_type = data["data_type"]
    value = validate_value(data_type, data["initial_value"])
    writable = data.get("writable", False)
    if not isinstance(writable, bool):
        raise ValueError("Writable 必须为布尔值")
    return {
        "node_id": node_id,
        "browse_name": browse_name,
        "data_type": data_type,
        "initial_value": value,
        "writable": writable,
    }
