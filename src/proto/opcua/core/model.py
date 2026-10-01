"""Plain Python validation for the M1 scalar variable model."""

import math
from typing import Any


def validate_variable(data: dict[str, Any]) -> dict[str, Any]:
    node_id = str(data["node_id"])
    if len(node_id) > 512 or not node_id.startswith("ns=2;s=") or not node_id[7:]:
        raise ValueError("M1 节点 ID 必须是最多 512 字符的 ns=2;s=... 字符串标识")
    browse_name = str(data["browse_name"]).strip()
    if not browse_name or len(browse_name) > 255:
        raise ValueError("BrowseName 必须在 1 到 255 个字符之间")
    data_type = data["data_type"]
    value = data["initial_value"]
    if data_type == "Boolean":
        if not isinstance(value, bool):
            raise ValueError("Boolean 初始值必须为布尔值")
    elif data_type == "Int32":
        if isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31:
            raise ValueError("Int32 初始值必须为 32 位整数")
    elif data_type == "Double":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Double 初始值必须为数值")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Double 初始值必须是有限数值")
    else:
        raise ValueError("M1 仅支持 Boolean、Int32、Double 变量")
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
