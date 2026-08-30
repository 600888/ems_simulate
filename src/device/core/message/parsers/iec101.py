"""Field-level IEC 60870-5-101 FT1.2 parser."""

from __future__ import annotations

from typing import Any

from src.proto.iec101.ft12 import FT12Codec, FT12Error, PrimaryFunction, SecondaryFunction

from .common import _fail, _field, _result, _validation
from .iec104 import parse_iec104


def parse_iec101(raw: bytes, *, role: str, link_address_size: int = 1) -> dict[str, Any]:
    result = _result("IEC 60870-5-101", raw)
    result["role"] = role.lower()
    codec = FT12Codec(link_address_size=link_address_size)
    try:
        frame = codec.decode(raw)
    except FT12Error:
        return _fail(result, "IEC101 FT1.2帧格式、长度或校验和无效")
    if frame.single_char_ack:
        result.update(frame_kind="单字符确认", summary="单字符确认 E5", purpose="链路层肯定确认")
        result["fields"].append(_field("ack", "单字符确认", 0, raw, "E5"))
        return result

    control = frame.control
    assert control is not None
    function_names = {
        **{int(value): value.name for value in PrimaryFunction},
        **{16 + int(value): value.name for value in SecondaryFunction},
    }
    function_key = int(control.function) if control.primary else 16 + int(control.function)
    function_name = function_names.get(function_key, f"FUNC_{control.function}")
    variable = raw[0] == 0x68
    body_offset = 4 if variable else 1
    fields = [
        _field("start", "启动字符", 0, raw[:1], f"0x{raw[0]:02X}"),
        _field("control", "链路控制域", body_offset, raw[body_offset : body_offset + 1], function_name),
        _field(
            "link_address",
            "链路地址",
            body_offset + 1,
            raw[body_offset + 1 : body_offset + 1 + codec.link_address_size],
            frame.link_address,
        ),
        _field("checksum", "校验和", len(raw) - 2, raw[-2:-1], f"0x{raw[-2]:02X}"),
        _field("end", "结束字符", len(raw) - 1, raw[-1:], "0x16"),
    ]
    result["fields"] = fields
    _validation(result, "FT1.2校验和", True, "控制域、链路地址及用户数据累加和正确")
    result["frame_kind"] = "可变帧" if variable else "固定帧"
    result["summary"] = f"{result['frame_kind']}，链路地址{frame.link_address}，{function_name}"
    result["purpose"] = function_name

    if not frame.user_data:
        return result

    # The ASDU begins at byte 6 for the usual one-byte IEC101 link address,
    # exactly where it begins in IEC104. Reuse the common ASDU field parser.
    fake = bytes([0x68, len(frame.user_data) + 4, 0, 0, 0, 0]) + frame.user_data
    parsed_asdu = parse_iec104(fake, role=role)
    asdu_offset = body_offset + 1 + codec.link_address_size
    delta = asdu_offset - 6
    for field in parsed_asdu.get("fields", []):
        if field.get("offset", 0) < 6:
            continue
        copied = dict(field)
        copied["offset"] = int(copied.get("offset", 0)) + delta
        result["fields"].append(copied)
    result["objects"] = parsed_asdu.get("objects", [])
    for obj in result["objects"]:
        obj["offset"] = int(obj.get("offset", 0)) + delta
        for field in obj.get("fields", []):
            field["offset"] = int(field.get("offset", 0)) + delta
    asdu_summary = parsed_asdu.get("summary", "")
    if "，" in asdu_summary:
        asdu_summary = asdu_summary.split("，", 2)[-1]
    result["summary"] += f"，{asdu_summary}"
    result["warnings"].extend(parsed_asdu.get("warnings", []))
    result["complete"] = parsed_asdu.get("complete", True)
    return result
