"""Field-level DL/T 645-2007 parser."""

from __future__ import annotations

from typing import Any

from .common import _fail, _field, _hex, _result, _validation

DLT_FUNCTIONS = {
    0x08: "广播校时",
    0x11: "读数据",
    0x12: "读后续数据",
    0x13: "读通信地址",
    0x14: "写数据",
    0x15: "写通信地址",
    0x17: "更改通信速率",
    0x18: "修改密码",
    0x19: "最大需量清零",
    0x1A: "电表清零",
    0x1B: "事件清零",
}


def _data_item_metadata(di: int) -> dict[str, Any] | None:
    """Resolve DI metadata from the protocol library without coupling capture to a running meter."""
    try:
        from dlt645.model.data.data_handler import get_data_item

        item = get_data_item(di)
        if isinstance(item, list):
            item = item[0] if item else None
        if item is None:
            return None
        return {
            "name": str(getattr(item, "name", "") or ""),
            "format": str(getattr(item, "data_format", "") or ""),
            "unit": str(getattr(item, "unit", "") or ""),
        }
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _decode_bcd(data: bytes, data_format: str) -> tuple[str | None, bool]:
    """Decode little-endian packed BCD according to a format such as XXX.X."""
    if not data or not data_format:
        return None, False
    digits: list[str] = []
    for byte in reversed(data):
        high, low = byte >> 4, byte & 0x0F
        if high > 9 or low > 9:
            return None, False
        digits.extend((str(high), str(low)))
    decimal_places = len(data_format.rsplit(".", 1)[1]) if "." in data_format else 0
    text = "".join(digits).lstrip("0") or "0"
    if decimal_places:
        text = text.zfill(decimal_places + 1)
        text = f"{text[:-decimal_places]}.{text[-decimal_places:]}"
    return text, True


def parse_dlt645(raw: bytes, *, role: str) -> dict[str, Any]:
    result = _result("DL/T 645-2007", raw)
    result["role"] = role.lower()
    start = next((i for i, byte in enumerate(raw) if byte == 0x68), -1)
    if start < 0 or len(raw) < start + 12:
        return _fail(result, "未找到完整的DL/T645帧")
    if start:
        result["fields"].append(_field("preamble", "前导符", 0, raw[:start], _hex(raw[:start]), "通常为FE"))
    fields = result["fields"]
    address_raw = raw[start + 1 : start + 7]
    address = "".join(f"{byte:02X}" for byte in reversed(address_raw))
    control, length = raw[start + 8], raw[start + 9]
    data_start, data_end = start + 10, start + 10 + length
    if len(raw) < data_end + 2:
        return _fail(result, f"数据域声明{length}字节，但报文长度不足")
    encoded, decoded = raw[data_start:data_end], bytes((byte - 0x33) & 0xFF for byte in raw[data_start:data_end])
    response, abnormal, more = bool(control & 0x80), bool(control & 0x40), bool(control & 0x20)
    function = control & 0x1F
    function_name = DLT_FUNCTIONS.get(function, f"未知功能0x{function:02X}")
    fields.extend(
        [
            _field("start", "起始符", start, raw[start : start + 1], "0x68"),
            _field("address", "电表地址", start + 1, address_raw, address, "BCD地址，低字节在前"),
            _field("start2", "第二起始符", start + 7, raw[start + 7 : start + 8], "0x68"),
            _field("control", "控制码", start + 8, raw[start + 8 : start + 9], f"0x{control:02X} {function_name}"),
            _field("length", "数据域长度", start + 9, raw[start + 9 : start + 10], length),
            _field("data_encoded", "传输数据域", data_start, encoded, _hex(encoded), "每字节均加0x33"),
            _field("data_decoded", "解码数据域", data_start, encoded, _hex(decoded), "传输字节逐个减0x33"),
        ]
    )
    if len(decoded) >= 4:
        di = int.from_bytes(decoded[:4], "little")
        metadata = _data_item_metadata(di)
        di_display = f"0x{di:08X}"
        if metadata and metadata["name"]:
            di_display += f" {metadata['name']}"
        fields.append(_field("data_identifier", "数据标识DI", data_start, encoded[:4], di_display, "解码后低字节在前"))
        value_bytes = decoded[4:]
        if value_bytes and not abnormal:
            value, bcd_valid = _decode_bcd(value_bytes, metadata["format"] if metadata else "")
            unit = metadata["unit"] if metadata else ""
            display_value = f"{value} {unit}".strip() if value is not None else _hex(value_bytes)
            fields.append(
                _field(
                    "data_value",
                    "数据值",
                    data_start + 4,
                    encoded[4:],
                    display_value,
                    f"解码字节: {_hex(value_bytes)}" + (f"，格式: {metadata['format']}" if metadata else ""),
                    "normal" if bcd_valid or not metadata else "warning",
                )
            )
            result["objects"].append(
                {
                    "index": 0,
                    "offset": data_start + 4,
                    "length": len(encoded[4:]),
                    "address": f"0x{di:08X}",
                    "value": value if value is not None else _hex(value_bytes),
                    "raw_value": _hex(encoded[4:]),
                    "quality": {"bcd_valid": bcd_valid} if metadata else None,
                    "timestamp": None,
                    "fields": [],
                    "name": metadata["name"] if metadata else "未知数据项",
                    "unit": unit,
                }
            )
            if metadata and not bcd_valid:
                result["warnings"].append("数据值不符合数据项定义的BCD格式")
        elif not metadata:
            result["warnings"].append(f"未找到DI 0x{di:08X}的数据项定义")
    if abnormal and decoded:
        error_code = decoded[0]
        error_bits = {
            0: "其他错误",
            1: "无请求数据",
            2: "密码错误或未授权",
            3: "通信速率不能更改",
            4: "年时区数超",
            5: "日时段数超",
            6: "费率数超",
        }
        reasons = [name for bit, name in error_bits.items() if error_code & (1 << bit)]
        fields.append(
            _field(
                "error_status",
                "异常状态字",
                data_start,
                encoded[:1],
                "、".join(reasons) or f"未知错误0x{error_code:02X}",
                level="error",
            )
        )
    checksum, calculated = raw[data_end], sum(raw[start:data_end]) & 0xFF
    fields.extend(
        [
            _field("checksum", "校验和CS", data_end, raw[data_end : data_end + 1], f"0x{checksum:02X}"),
            _field("end", "结束符", data_end + 1, raw[data_end + 1 : data_end + 2], f"0x{raw[data_end + 1]:02X}"),
        ]
    )
    _validation(result, "第一起始符", raw[start] == 0x68, "应为0x68")
    _validation(result, "第二起始符", raw[start + 7] == 0x68, f"实际0x{raw[start + 7]:02X}")
    _validation(result, "校验和", checksum == calculated, f"报文0x{checksum:02X}，计算0x{calculated:02X}")
    _validation(result, "结束符", raw[data_end + 1] == 0x16, f"实际0x{raw[data_end + 1]:02X}")
    direction = "从站响应" if response else "主站命令"
    flags = ("，异常响应" if abnormal else "") + ("，有后续帧" if more else "")
    result["frame_kind"] = direction
    result["summary"] = f"{direction}：电表{address}{function_name}{flags}，数据域{length}字节"
    result["purpose"] = function_name
    return result
