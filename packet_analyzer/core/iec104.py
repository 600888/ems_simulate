"""Field-level IEC 60870-5-104 parser."""

from __future__ import annotations

from typing import Any

from .common import _fail, _field, _hex, _result, _validation

IEC_TYPES = {
    1: "M_SP_NA_1 单点遥信",
    2: "M_SP_TA_1 单点遥信(CP16)",
    3: "M_DP_NA_1 双点遥信",
    4: "M_DP_TA_1 双点遥信(CP16)",
    9: "M_ME_NA_1 归一化遥测",
    11: "M_ME_NB_1 标度化遥测",
    13: "M_ME_NC_1 短浮点遥测",
    15: "M_IT_NA_1 累计量",
    21: "M_ME_ND_1 归一化遥测(无品质)",
    30: "M_SP_TB_1 单点遥信(CP56)",
    31: "M_DP_TB_1 双点遥信(CP56)",
    34: "M_ME_TD_1 归一化遥测(CP56)",
    35: "M_ME_TE_1 标度化遥测(CP56)",
    36: "M_ME_TF_1 短浮点遥测(CP56)",
    37: "M_IT_TB_1 累计量(CP56)",
    45: "C_SC_NA_1 单点遥控",
    46: "C_DC_NA_1 双点遥控",
    47: "C_RC_NA_1 步调节",
    48: "C_SE_NA_1 归一化设点",
    49: "C_SE_NB_1 标度化设点",
    50: "C_SE_NC_1 短浮点设点",
    58: "C_SC_TA_1 单点遥控(CP56)",
    59: "C_DC_TA_1 双点遥控(CP56)",
    60: "C_RC_TA_1 步调节(CP56)",
    61: "C_SE_TA_1 归一化设点(CP56)",
    62: "C_SE_TB_1 标度化设点(CP56)",
    63: "C_SE_TC_1 短浮点设点(CP56)",
    100: "C_IC_NA_1 总召唤",
    101: "C_CI_NA_1 电度量召唤",
    102: "C_RD_NA_1 读命令",
    103: "C_CS_NA_1 时钟同步",
    104: "C_TS_NA_1 测试命令",
    105: "C_RP_NA_1 复位进程",
    106: "C_CD_NA_1 延时获得",
    107: "C_TS_TA_1 测试命令(CP56)",
}
IEC_COT = {
    1: "周期",
    2: "背景扫描",
    3: "突发/自发",
    4: "初始化",
    5: "请求",
    6: "激活",
    7: "激活确认",
    8: "停止激活",
    9: "停止激活确认",
    10: "激活终止",
    20: "响应总召唤",
}


def parse_iec104(raw: bytes, *, role: str) -> dict[str, Any]:
    result = _result("IEC 60870-5-104", raw)
    result["role"] = role.lower()
    if len(raw) < 6 or raw[0] != 0x68:
        return _fail(result, "IEC104报文起始符或长度无效")
    fields = result["fields"]
    fields.extend(
        [
            _field("start", "启动字符", 0, raw[:1], "0x68"),
            _field("apdu_length", "APDU长度", 1, raw[1:2], raw[1], "控制域及ASDU长度"),
        ]
    )
    _validation(result, "APDU长度", raw[1] == len(raw) - 2, f"声明{raw[1]}字节，实际{len(raw) - 2}字节")
    ctrl = raw[2:6]
    if ctrl[0] & 0x03 == 0x03:
        commands = {
            0x07: "STARTDT_ACT 启动数据传输",
            0x0B: "STARTDT_CON 启动确认",
            0x13: "STOPDT_ACT 停止数据传输",
            0x23: "STOPDT_CON 停止确认",
            0x43: "TESTFR_ACT 测试请求",
            0x83: "TESTFR_CON 测试确认",
        }
        command = commands.get(ctrl[0], f"未知U帧0x{ctrl[0]:02X}")
        fields.append(_field("control", "U帧控制域", 2, ctrl, command))
        result.update(frame_kind="U格式帧", summary=f"U格式帧：{command}", purpose=command)
        return result
    if ctrl[0] & 0x01:
        nr = int.from_bytes(ctrl[2:4], "little") >> 1
        fields.extend(
            [
                _field("control", "S帧控制域", 2, ctrl, "监督帧"),
                _field("receive_sequence", "接收序号N(R)", 4, ctrl[2:4], nr),
            ]
        )
        result.update(
            frame_kind="S格式帧", summary=f"S格式确认帧，已正确接收到序号{nr - 1}", purpose="确认已接收的I格式帧"
        )
        return result
    ns, nr = int.from_bytes(ctrl[:2], "little") >> 1, int.from_bytes(ctrl[2:4], "little") >> 1
    fields.extend(
        [
            _field("send_sequence", "发送序号N(S)", 2, ctrl[:2], ns),
            _field("receive_sequence", "接收序号N(R)", 4, ctrl[2:4], nr),
        ]
    )
    result["frame_kind"] = "I格式帧"
    if len(raw) < 12:
        return _fail(result, "I格式帧缺少完整ASDU")
    asdu, base = raw[6:], 6
    type_id, vsq = asdu[0], asdu[1]
    count, sequential = vsq & 0x7F, bool(vsq & 0x80)
    cot, negative, test = asdu[2] & 0x3F, bool(asdu[2] & 0x40), bool(asdu[2] & 0x80)
    originator, common = asdu[3], int.from_bytes(asdu[4:6], "little")
    type_name, cot_name = IEC_TYPES.get(type_id, f"未知Type ID {type_id}"), IEC_COT.get(cot, f"COT {cot}")
    fields.extend(
        [
            _field("type_id", "类型标识Type ID", base, asdu[:1], f"{type_id} {type_name}"),
            _field("vsq", "可变结构限定词VSQ", base + 1, asdu[1:2], f"对象数{count}，SQ={int(sequential)}"),
            _field(
                "cot",
                "传送原因COT",
                base + 2,
                asdu[2:4],
                f"{cot} {cot_name}" + ("，否定" if negative else "") + ("，测试" if test else ""),
            ),
            _field("originator", "源发地址", base + 3, asdu[3:4], originator),
            _field("common_address", "公共地址", base + 4, asdu[4:6], common),
        ]
    )
    _parse_iec_objects(result, asdu[6:], base + 6, type_id, count, sequential)
    result["summary"] = f"I格式帧N(S)={ns}、N(R)={nr}，公共地址{common}，{type_name}，{cot_name}，{count}个信息体"
    result["purpose"] = f"以{cot_name}方式传送{type_name}"
    return result


def _decode_quality(value: int) -> dict[str, Any]:
    return {
        "raw": f"0x{value:02X}",
        "overflow": bool(value & 0x01),
        "blocked": bool(value & 0x10),
        "substituted": bool(value & 0x20),
        "not_topical": bool(value & 0x40),
        "invalid": bool(value & 0x80),
    }


def _decode_cp16(data: bytes) -> tuple[str, dict[str, Any]]:
    milliseconds = int.from_bytes(data[:2], "little")
    return f"{milliseconds / 1000:.3f}s", {"milliseconds": milliseconds}


def _decode_cp56(data: bytes) -> tuple[str, dict[str, Any]]:
    milliseconds = int.from_bytes(data[:2], "little")
    second, millisecond = divmod(milliseconds, 1000)
    minute, invalid = data[2] & 0x3F, bool(data[2] & 0x80)
    hour, summer_time = data[3] & 0x1F, bool(data[3] & 0x80)
    day, day_of_week = data[4] & 0x1F, (data[4] >> 5) & 0x07
    month, year = data[5] & 0x0F, 2000 + (data[6] & 0x7F)
    text = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}.{millisecond:03d}"
    return text, {
        "year": year,
        "month": month,
        "day": day,
        "day_of_week": day_of_week,
        "hour": hour,
        "minute": minute,
        "second": second,
        "millisecond": millisecond,
        "invalid": invalid,
        "summer_time": summer_time,
    }


def _object_layout(type_id: int) -> tuple[str, int, str | None, int]:
    layouts = {
        1: ("single", 1, "embedded", 0),
        2: ("single", 1, "embedded", 2),
        3: ("double", 1, "embedded", 0),
        4: ("double", 1, "embedded", 2),
        9: ("normalized", 2, "qds", 0),
        11: ("scaled", 2, "qds", 0),
        13: ("float", 4, "qds", 0),
        15: ("counter", 4, "bcr", 0),
        21: ("normalized", 2, None, 0),
        30: ("single", 1, "embedded", 7),
        31: ("double", 1, "embedded", 7),
        34: ("normalized", 2, "qds", 7),
        35: ("scaled", 2, "qds", 7),
        36: ("float", 4, "qds", 7),
        37: ("counter", 4, "bcr", 7),
        45: ("single_command", 1, "command_embedded", 0),
        46: ("double_command", 1, "command_embedded", 0),
        47: ("step_command", 1, "command_embedded", 0),
        48: ("normalized", 2, "command", 0),
        49: ("scaled", 2, "command", 0),
        50: ("float", 4, "command", 0),
        58: ("single_command", 1, "command_embedded", 7),
        59: ("double_command", 1, "command_embedded", 7),
        60: ("step_command", 1, "command_embedded", 7),
        61: ("normalized", 2, "command", 7),
        62: ("scaled", 2, "command", 7),
        63: ("float", 4, "command", 7),
        100: ("qoi", 1, None, 0),
        101: ("qcc", 1, None, 0),
        102: ("none", 0, None, 0),
        103: ("none", 0, None, 7),
        104: ("uint16", 2, None, 0),
        105: ("u8", 1, None, 0),
        106: ("none", 0, None, 2),
        107: ("uint16", 2, None, 7),
    }
    return layouts[type_id]


def _decode_value(kind: str, data: bytes) -> Any:
    import struct

    if kind in ("single", "single_command"):
        return bool(data[0] & 0x01)
    if kind in ("double", "double_command"):
        return data[0] & 0x03
    if kind == "step_command":
        return data[0] & 0x03
    if kind == "normalized":
        return round(int.from_bytes(data[:2], "little", signed=True) / 32767, 6)
    if kind == "scaled":
        return int.from_bytes(data[:2], "little", signed=True)
    if kind == "float":
        return struct.unpack("<f", data[:4])[0]
    if kind == "counter":
        return int.from_bytes(data[:4], "little", signed=True)
    if kind == "uint16":
        return int.from_bytes(data[:2], "little")
    if kind == "u8":
        return data[0]
    if kind == "qoi":
        return f"QOI={data[0]}"
    if kind == "qcc":
        return {"request": data[0] & 0x3F, "freeze": (data[0] >> 6) & 0x03}
    return None


def _parse_iec_objects(
    result: dict[str, Any], payload: bytes, offset: int, type_id: int, count: int, sequential: bool
) -> None:
    try:
        kind, value_size, qualifier_kind, time_size = _object_layout(type_id)
    except KeyError:
        result["complete"] = False
        result["warnings"].append("该ASDU类型的信息体值尚未完全解析")
        return

    cursor, first_ioa = 0, None
    qualifier_size = 1 if qualifier_kind in ("qds", "command", "bcr") else 0
    object_size = value_size + qualifier_size + time_size
    for index in range(count):
        object_start = cursor
        if not sequential or index == 0:
            if cursor + 3 > len(payload):
                result["complete"] = False
                result["warnings"].append(f"第{index + 1}个信息体缺少IOA")
                break
            ioa = int.from_bytes(payload[cursor : cursor + 3], "little")
            first_ioa = ioa
            cursor += 3
        else:
            ioa = int(first_ioa or 0) + index
        data_start = cursor
        if cursor + object_size > len(payload):
            result["complete"] = False
            result["warnings"].append(f"第{index + 1}个信息体数据不完整")
            break

        value_raw = payload[cursor : cursor + value_size]
        value = _decode_value(kind, value_raw)
        cursor += value_size
        quality = None
        object_fields = [
            _field(
                "ioa",
                "信息对象地址IOA",
                offset + object_start,
                payload[object_start : object_start + 3] if not sequential or index == 0 else b"",
                ioa,
                "SQ=1的后续IOA由首地址递增" if sequential and index > 0 else "",
            ),
            _field("value", "信息体值", offset + data_start, value_raw, value),
        ]

        if qualifier_kind == "embedded" and value_raw:
            quality = _decode_quality(value_raw[0] & 0xF0)
            object_fields.append(_field("quality", "品质描述词", offset + data_start, value_raw[:1], quality))
        elif qualifier_kind == "qds":
            qualifier_raw = payload[cursor : cursor + 1]
            quality = _decode_quality(qualifier_raw[0])
            object_fields.append(_field("quality", "品质描述词QDS", offset + cursor, qualifier_raw, quality))
            cursor += 1
        elif qualifier_kind == "bcr":
            qualifier_raw = payload[cursor : cursor + 1]
            qualifier = qualifier_raw[0]
            quality = {
                "raw": f"0x{qualifier:02X}",
                "sequence": qualifier & 0x1F,
                "carry": bool(qualifier & 0x20),
                "adjusted": bool(qualifier & 0x40),
                "invalid": bool(qualifier & 0x80),
            }
            object_fields.append(
                _field("binary_counter_quality", "累计量品质BCR", offset + cursor, qualifier_raw, quality)
            )
            cursor += 1
        elif qualifier_kind in ("command", "command_embedded"):
            if qualifier_kind == "command_embedded":
                qualifier_raw = value_raw[-1:]
                qualifier_offset = data_start + value_size - 1
            else:
                qualifier_raw = payload[cursor : cursor + 1]
                qualifier_offset = cursor
            qualifier = qualifier_raw[0]
            quality = {
                "raw": f"0x{qualifier:02X}",
                "select": bool(qualifier & 0x80),
                "qualifier": (qualifier >> 2) & 0x1F if qualifier_kind == "command_embedded" else qualifier & 0x7F,
            }
            object_fields.append(
                _field("command_qualifier", "命令限定词", offset + qualifier_offset, qualifier_raw, quality)
            )
            if qualifier_kind == "command":
                cursor += 1

        timestamp = None
        timestamp_meta = None
        if time_size:
            time_raw = payload[cursor : cursor + time_size]
            if time_size == 2:
                timestamp, timestamp_meta = _decode_cp16(time_raw)
                time_name = "CP16Time2a"
            else:
                timestamp, timestamp_meta = _decode_cp56(time_raw)
                time_name = "CP56Time2a"
            object_fields.append(
                _field("timestamp", time_name, offset + cursor, time_raw, timestamp, str(timestamp_meta))
            )
            cursor += time_size

        full_raw = payload[data_start:cursor]
        result["objects"].append(
            {
                "index": index,
                "offset": offset + object_start,
                "length": cursor - object_start,
                "address": ioa,
                "value": value,
                "raw_value": _hex(full_raw),
                "quality": quality,
                "timestamp": timestamp,
                "timestamp_detail": timestamp_meta,
                "fields": object_fields,
            }
        )

    if cursor < len(payload):
        result["warnings"].append(f"信息体后仍有{len(payload) - cursor}个未解释字节")
