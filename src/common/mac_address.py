"""MAC 地址输入规范化。"""

from __future__ import annotations

from collections.abc import Sequence
import json
import re
from typing import Any


def normalize_mac_address(value: Any) -> list[int] | None:
    """将文本、JSON、字节序列或数字序列统一为六字节整数列表。"""
    if value is None or value == "":
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text[0] in '["':
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = text
            if decoded != text:
                return normalize_mac_address(decoded)
        parts: Sequence[Any] = re.split(r"[:-]", text)
        if len(parts) != 6:
            raise ValueError(f"MAC 地址必须包含 6 个字节: {value!r}")
        bytes_value = [int(str(part), 16) for part in parts]
    elif isinstance(value, (bytes, bytearray, list, tuple)):
        if len(value) != 6:
            raise ValueError(f"MAC 地址必须包含 6 个字节: {value!r}")
        bytes_value = []
        for part in value:
            if isinstance(part, bool):
                raise ValueError(f"MAC 地址字节不能是布尔值: {value!r}")
            if isinstance(part, str):
                bytes_value.append(int(part, 16))
            else:
                bytes_value.append(int(part))
    else:
        raise ValueError(f"不支持的 MAC 地址类型: {type(value).__name__}")

    if any(byte < 0 or byte > 0xFF for byte in bytes_value):
        raise ValueError(f"MAC 地址字节超出 0..255: {value!r}")
    return bytes_value


def format_mac_address(value: Any) -> str:
    """返回统一的大写冒号格式；空值返回空字符串。"""
    normalized = normalize_mac_address(value)
    return ":".join(f"{byte:02X}" for byte in normalized) if normalized else ""
