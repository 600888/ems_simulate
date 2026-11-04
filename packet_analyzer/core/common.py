"""Shared result builders for protocol message parsers."""

from __future__ import annotations

from typing import Any


def _hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def _field(
    key: str,
    name: str,
    offset: int,
    raw: bytes,
    value: Any,
    description: str = "",
    level: str = "normal",
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "offset": offset,
        "length": len(raw),
        "raw_hex": _hex(raw),
        "value": value,
        "display_value": str(value),
        "description": description,
        "level": level,
    }


def _result(protocol: str, raw: bytes) -> dict[str, Any]:
    return {
        "protocol": protocol,
        "frame_kind": "未知帧",
        "role": "unknown",
        "summary": "无法识别该报文",
        "purpose": "",
        "valid": True,
        "complete": True,
        "raw_hex": _hex(raw),
        "raw_length": len(raw),
        "fields": [],
        "objects": [],
        "validation": [],
        "correlation": None,
        "warnings": [],
        "errors": [],
    }


def _validation(result: dict[str, Any], name: str, passed: bool, detail: str) -> None:
    result["validation"].append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        result["valid"] = False


def _fail(result: dict[str, Any], message: str) -> dict[str, Any]:
    result["valid"] = False
    result["complete"] = False
    result["errors"].append(message)
    result["summary"] = message
    return result
