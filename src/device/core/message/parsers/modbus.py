"""Field-level Modbus TCP/RTU parser."""

from __future__ import annotations

from typing import Any

from .common import _fail, _field, _hex, _result, _validation

MODBUS_FUNCTIONS = {
    1: "读线圈",
    2: "读离散输入",
    3: "读保持寄存器",
    4: "读输入寄存器",
    5: "写单个线圈",
    6: "写单个寄存器",
    15: "写多个线圈",
    16: "写多个寄存器",
}
MODBUS_EXCEPTIONS = {
    1: "非法功能码",
    2: "非法数据地址",
    3: "非法数据值",
    4: "从站设备故障",
    5: "确认",
    6: "从站设备忙",
    8: "存储奇偶校验错误",
    10: "网关路径不可用",
    11: "网关目标设备未响应",
}


def _crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def parse_modbus(
    raw: bytes,
    *,
    tcp: bool,
    role: str,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _result("Modbus TCP" if tcp else "Modbus RTU", raw)
    result["role"] = role.lower()
    fields = result["fields"]
    if tcp:
        if len(raw) < 8:
            return _fail(result, "Modbus TCP报文不足8字节")
        transaction = int.from_bytes(raw[0:2], "big")
        protocol_id = int.from_bytes(raw[2:4], "big")
        declared = int.from_bytes(raw[4:6], "big")
        unit = raw[6]
        fields.extend(
            [
                _field("transaction_id", "事务标识", 0, raw[0:2], transaction, "用于匹配请求和响应"),
                _field("protocol_id", "协议标识", 2, raw[2:4], protocol_id, "Modbus TCP固定为0"),
                _field("length", "后续长度", 4, raw[4:6], declared, "Unit ID与PDU的总长度"),
                _field("unit_id", "单元标识", 6, raw[6:7], unit, "从站地址"),
            ]
        )
        _validation(result, "MBAP长度", declared == len(raw) - 6, f"声明{declared}字节，实际{len(raw) - 6}字节")
        _validation(result, "协议标识", protocol_id == 0, f"值为{protocol_id}")
        pdu, pdu_offset = raw[7:], 7
    else:
        if len(raw) < 4:
            return _fail(result, "Modbus RTU报文不足4字节")
        unit = raw[0]
        fields.append(_field("slave_id", "从站地址", 0, raw[0:1], unit))
        received_crc = int.from_bytes(raw[-2:], "little")
        calculated_crc = _crc16_modbus(raw[:-2])
        fields.append(_field("crc", "CRC16", len(raw) - 2, raw[-2:], f"0x{received_crc:04X}", "低字节在前"))
        _validation(
            result,
            "CRC16",
            received_crc == calculated_crc,
            f"报文0x{received_crc:04X}，计算0x{calculated_crc:04X}",
        )
        pdu, pdu_offset = raw[1:-2], 1
    if not pdu:
        return _fail(result, "PDU为空")
    fc = pdu[0]
    exception = bool(fc & 0x80)
    base_fc = fc & 0x7F
    function_name = MODBUS_FUNCTIONS.get(base_fc, f"未知功能码0x{base_fc:02X}")
    fields.append(_field("function_code", "功能码", pdu_offset, pdu[:1], f"0x{fc:02X} {function_name}"))
    result["frame_kind"] = "异常响应" if exception else ("请求帧" if role == "Request" else "响应帧")
    if request_context:
        result["correlation"] = request_context
    if exception:
        code = pdu[1] if len(pdu) > 1 else None
        name = MODBUS_EXCEPTIONS.get(code, "未知异常") if code is not None else "缺少异常码"
        if code is not None:
            fields.append(
                _field("exception_code", "异常码", pdu_offset + 1, pdu[1:2], f"0x{code:02X} {name}", level="error")
            )
        result["summary"] = f"从站{unit}返回{function_name}异常：{name}"
        result["purpose"] = "报告请求执行失败"
        return result
    _parse_modbus_pdu(result, pdu, pdu_offset, unit, base_fc, function_name, role, request_context)
    return result


def _parse_modbus_pdu(
    result: dict[str, Any],
    pdu: bytes,
    offset: int,
    unit: int,
    fc: int,
    name: str,
    role: str,
    request_context: dict[str, Any] | None,
) -> None:
    fields, objects = result["fields"], result["objects"]
    is_request = role == "Request"
    if fc in (1, 2, 3, 4) and is_request and len(pdu) >= 5:
        start, count = int.from_bytes(pdu[1:3], "big"), int.from_bytes(pdu[3:5], "big")
        fields.extend(
            [
                _field("start_address", "起始地址", offset + 1, pdu[1:3], f"{start} (0x{start:04X})"),
                _field("quantity", "数量", offset + 3, pdu[3:5], count),
            ]
        )
        result["summary"] = f"主站请求从站{unit}{name}，地址0x{start:04X}～0x{start + count - 1:04X}，共{count}个"
        result["purpose"] = name
    elif fc in (1, 2, 3, 4) and not is_request and len(pdu) >= 2:
        count = pdu[1]
        payload = pdu[2 : 2 + count]
        fields.append(_field("byte_count", "数据字节数", offset + 1, pdu[1:2], count))
        fields.append(_field("data", "数据域", offset + 2, payload, _hex(payload)))
        if fc in (3, 4):
            for index in range(0, len(payload) - 1, 2):
                value = int.from_bytes(payload[index : index + 2], "big")
                address = request_context["start_address"] + index // 2 if request_context else None
                objects.append(
                    {
                        "index": index // 2,
                        "offset": offset + 2 + index,
                        "length": 2,
                        "address": address,
                        "value": value,
                        "raw_value": _hex(payload[index : index + 2]),
                        "quality": None,
                        "timestamp": None,
                        "fields": [],
                    }
                )
        else:
            expected = int(request_context.get("quantity", count * 8)) if request_context else count * 8
            for index in range(min(count * 8, expected)):
                address = request_context["start_address"] + index if request_context else None
                objects.append(
                    {
                        "index": index,
                        "offset": offset + 2 + index // 8,
                        "length": 1,
                        "address": address,
                        "value": bool(payload[index // 8] & (1 << (index % 8))),
                        "raw_value": None,
                        "quality": None,
                        "timestamp": None,
                        "fields": [],
                    }
                )
        _validation(result, "数据长度", len(payload) == count, f"声明{count}字节，实际{len(payload)}字节")
        result["summary"] = f"从站{unit}返回{name}响应，包含{len(objects)}个值"
        result["purpose"] = f"返回{name}数据"
    elif fc in (5, 6) and len(pdu) >= 5:
        address, value = int.from_bytes(pdu[1:3], "big"), int.from_bytes(pdu[3:5], "big")
        display = (
            ("合闸/ON" if value == 0xFF00 else "分闸/OFF" if value == 0 else f"非法线圈值0x{value:04X}")
            if fc == 5
            else f"{value} (0x{value:04X})"
        )
        fields.extend(
            [
                _field("address", "目标地址", offset + 1, pdu[1:3], f"{address} (0x{address:04X})"),
                _field("value", "写入值", offset + 3, pdu[3:5], display),
            ]
        )
        result["summary"] = (
            f"{'主站写入' if is_request else '从站确认写入'}从站{unit}地址0x{address:04X}，值为{display}"
        )
        result["purpose"] = name
    elif fc in (15, 16) and len(pdu) >= 5:
        start, quantity = int.from_bytes(pdu[1:3], "big"), int.from_bytes(pdu[3:5], "big")
        fields.extend(
            [
                _field("start_address", "起始地址", offset + 1, pdu[1:3], f"{start} (0x{start:04X})"),
                _field("quantity", "数量", offset + 3, pdu[3:5], quantity),
            ]
        )
        if is_request and len(pdu) >= 6:
            byte_count, payload = pdu[5], pdu[6 : 6 + pdu[5]]
            fields.extend(
                [
                    _field("byte_count", "数据字节数", offset + 5, pdu[5:6], byte_count),
                    _field("data", "写入数据", offset + 6, payload, _hex(payload)),
                ]
            )
        action = "主站请求" if is_request else "从站确认"
        address_range = f"0x{start:04X}～0x{start + quantity - 1:04X}"
        result["summary"] = f"{action}{name}，从站{unit}，地址{address_range}"
        result["purpose"] = name
    else:
        result["complete"] = False
        result["warnings"].append("该功能码的数据域尚未完全解析")
        result["summary"] = f"从站{unit}，{name}，PDU长度{len(pdu)}字节"
