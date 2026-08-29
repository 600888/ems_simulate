"""DNP3 (IEEE 1815) 报文解析器：链路层 / 传输层 / 应用层逐字段解析。"""

from __future__ import annotations

import struct
from typing import Any

from .common import _fail, _field, _hex, _result, _validation

_PRIMARY_LINK_FUNCTIONS = {
    0: "复位远程链路 (RESET_LINK_STATES)",
    1: "复位用户进程 (RESET_USER_PROCESS)",
    2: "测试链路状态 (TEST_LINK_STATES)",
    3: "确认用户数据 (CONFIRMED_USER_DATA)",
    4: "无确认用户数据 (UNCONFIRMED_USER_DATA)",
    9: "请求链路状态 (REQUEST_LINK_STATUS)",
}
_SECONDARY_LINK_FUNCTIONS = {
    0: "确认 (ACK)",
    1: "否定确认 (NACK)",
    11: "链路状态 (LINK_STATUS)",
    14: "不支持 (NOT_SUPPORTED)",
}

DNP3_FUNCTION_CODES = {
    0: "确认 (Confirm)",
    1: "读 (Read)",
    2: "写 (Write)",
    3: "选择 (Select)",
    4: "操作 (Operate)",
    5: "直接操作 (Direct Operate)",
    6: "直接操作-无确认 (Direct Operate, No Ack)",
    7: "冻结 (Freeze)",
    8: "冻结-无确认 (Freeze, No Ack)",
    9: "冻结并清除 (Freeze, Clear)",
    10: "冻结并清除-无确认 (Freeze, Clear, No Ack)",
    11: "定时冻结 (Freeze at Time)",
    12: "定时冻结-无确认 (Freeze at Time, No Ack)",
    13: "冷重启 (Cold Restart)",
    14: "热重启 (Warm Restart)",
    15: "初始化数据 (Initialize Data)",
    16: "初始化应用 (Initialize Application)",
    17: "启动应用 (Start Application)",
    18: "停止应用 (Stop Application)",
    19: "保存配置 (Save Configuration)",
    20: "使能未请求上报 (Enable Unsolicited)",
    21: "禁止未请求上报 (Disable Unsolicited)",
    22: "分配类 (Assign Class)",
    23: "延迟测量 (Delay Measure)",
    24: "记录当前时间 (Record Current Time)",
    25: "打开文件 (Open File)",
    26: "关闭文件 (Close File)",
    27: "删除文件 (Delete File)",
    28: "获取文件信息 (Get File Info)",
    29: "文件认证 (Authenticate File)",
    30: "中止文件操作 (Abort File)",
    129: "响应：成功",
    130: "未请求响应 (Unsolicited Response)",
}

_KNOWN_FUNCTION_CODES = frozenset(DNP3_FUNCTION_CODES)

DNP3_OBJECT_GROUPS = {
    1: "二进制输入",
    2: "二进制输入事件",
    11: "二进制输出状态事件",
    13: "二进制输出命令事件",
    10: "二进制输出状态",
    12: "二进制输出命令",
    20: "计数器",
    21: "冻结计数器",
    22: "计数器事件",
    23: "冻结计数器事件",
    30: "模拟量输入",
    31: "冻结模拟量输入",
    32: "模拟量输入事件",
    33: "冻结模拟量输入事件",
    34: "模拟量输入死区",
    40: "模拟量输出状态",
    41: "模拟量输出命令",
    42: "模拟量输出状态事件",
    43: "模拟量输出命令事件",
    50: "日期时间",
    51: "CTO 公共时间",
    52: "时间延迟",
    60: "类数据",
    80: "内部指示",
}

# 这些请求只携带对象选择范围，不携带对象值。
_SELECTOR_FUNCTION_CODES = frozenset({1, 7, 8, 9, 10, 11, 12, 20, 21, 22})

# 功能码 → 请求 (主->从) 或响应
_RESPONSE_FC_START = 129


def _crc16_dnp3(data: bytes) -> int:
    """DNP3 专有 CRC16（与 pydnp3_pure.link.crc 一致，查表 + 取反）。

    优先复用库实现（本项目已依赖 pydnp3-pure），避免两套实现漂移。
    """
    try:
        from pydnp3_pure.link.crc import compute_crc

        return compute_crc(data)
    except Exception:
        # 兜底：本地实现（多项式 0x3D65 反向 0xA6BC，初值 0，计算后取反）
        crc = 0x0000
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x3D65) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return (~crc) & 0xFFFF


def _check_crc_block(data: bytes, start: int, payload_len: int) -> bool:
    """校验 data[start:start+payload_len] 的 CRC（CRC 紧跟在 payload 之后 2 字节）。"""
    payload = data[start : start + payload_len]
    if start + payload_len + 2 > len(data):
        return False
    received = int.from_bytes(data[start + payload_len : start + payload_len + 2], "little")
    return _crc16_dnp3(payload) == received


def parse_dnp3(
    raw: bytes,
    *,
    role: str = "",
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解析 DNP3 报文。

    支持完整链路层帧（0x0564 起始字 + CRC 校验），
    并尽量解析传输层与应用层（若报文完整）。
    """
    result = _result("DNP3", raw)
    result["role"] = role.lower()
    fields = result["fields"]

    # ---- 链路层 ----
    if len(raw) < 10:
        return _fail(result, "DNP3 链路层报文不足 10 字节")

    if raw[0:2] != b"\x05\x64":
        return _fail(result, "DNP3 起始字应为 0x05 0x64")
    fields.append(_field("start", "起始字", 0, raw[0:2], "0x0564", "DNP3 固定起始字"))

    length = raw[2]
    if length < 5 or length > 255:
        return _fail(result, f"DNP3 长度字段非法: {length}")
    fields.append(_field("length", "长度", 2, raw[2:3], length, "控制字+地址+数据的总长度"))

    ctrl = raw[3]
    fields.append(_field("link_control", "链路控制字", 3, raw[3:4], f"0x{ctrl:02X}", _link_control_desc(ctrl)))

    # DNP3 帧布局（2 字节地址）：
    #   起始字(2) + length(1) + ctrl(1) + 目的地址(2) + 源地址(2) +
    #   头CRC(2，对 ctrl+地址) + 用户数据块(≤16字节) + 块CRC(2) ...
    #  length = 1(ctrl) + 4(地址) + 用户数据字节数
    addr_size = 2
    header_payload_len = 1 + addr_size * 2  # ctrl + 目的地址 + 源地址 = 5，位于 raw[3:8]
    header_crc_off = 3 + header_payload_len  # 头 CRC 位于 raw[8:10]
    # 用户数据区从 头CRC 之后 开始
    user_data_start = header_crc_off + 2  # = 10
    user_data_length = length - header_payload_len
    expected_body_length = user_data_length + 2 * ((user_data_length + 15) // 16)
    user_data_raw = raw[user_data_start : user_data_start + expected_body_length]
    if len(user_data_raw) < expected_body_length:
        result["complete"] = False
        result["warnings"].append(f"链路层数据不完整：应有 {expected_body_length} 字节，实际 {len(user_data_raw)} 字节")

    if len(raw) >= 4 + addr_size * 2:
        dst = int.from_bytes(raw[4 : 4 + addr_size], "little")
        src = int.from_bytes(raw[4 + addr_size : 4 + 2 * addr_size], "little")
        fields.append(_field("dest_address", "目的地址", 4, raw[4 : 4 + addr_size], dst, "DNP3 站点地址"))
        fields.append(
            _field("src_address", "源地址", 4 + addr_size, raw[4 + addr_size : 4 + 2 * addr_size], src, "DNP3 站点地址")
        )

    # 头部 CRC 校验：DNP3 链路头 CRC 对整个 8 字节头（起始字+长度+控制字+地址）计算，
    # 与 pydnp3_pure 的 serialize() 一致（compute_crc(header_block)）。
    _validation(
        result,
        "链路头CRC",
        _check_crc_block(raw, 0, 8),
        "链路头 CRC 通过",
    )

    # 用户数据块 CRC 校验（每 ≤16 字节一块 + 2 字节 CRC）
    block_errors: list[str] = []
    pos = 0
    remaining = user_data_length
    block_idx = 0
    while remaining > 0:
        block_data_len = min(remaining, 16)
        if not _check_crc_block(user_data_raw, pos, block_data_len):
            block_errors.append(f"块{block_idx} CRC错或数据不完整")
        pos += block_data_len + 2
        remaining -= block_data_len
        block_idx += 1
    _validation(
        result,
        "数据块CRC",
        not block_errors,
        "全部CRC通过" if not block_errors else ", ".join(block_errors),
    )

    # 用户数据 = 去掉各块尾部的 CRC
    user_data = bytearray()
    pos = 0
    remaining = user_data_length
    while remaining > 0:
        block_data_len = min(remaining, 16)
        available = min(block_data_len, max(len(user_data_raw) - pos, 0))
        user_data.extend(user_data_raw[pos : pos + available])
        if available < block_data_len:
            break
        pos += block_data_len + 2
        remaining -= block_data_len

    result["frame_kind"] = "链路数据帧"
    result["purpose"] = "从站→主站数据" if _link_is_server_data(ctrl) else "链路层数据帧"

    # ---- 传输层 / 应用层 ----
    app_offset = 0
    if _has_transport_header(user_data):
        transport = user_data[0]
        transport_fir = bool(transport & 0x80)
        transport_fin = bool(transport & 0x40)
        transport_seq = transport & 0x3F
        fields.append(
            _field(
                "transport_control",
                "传输控制字",
                user_data_start,
                bytes([transport]),
                f"0x{transport:02X}",
                f"FIR={transport_fir} FIN={transport_fin} SEQ={transport_seq}",
            )
        )
        app_offset = 1
        if not transport_fir:
            result["frame_kind"] = "传输层后续分段"
            result["summary"] = f"DNP3传输层后续分段 SEQ={transport_seq}"
            result["purpose"] = "传输层分段数据"
            result["complete"] = False
            result["warnings"].append("当前链路帧不包含应用层首部，需结合前序分段解析")
            if request_context:
                result["correlation"] = request_context
            return result

    if len(user_data) > app_offset:
        app_ctrl = user_data[app_offset]
        seq = app_ctrl & 0x0F
        fir = bool(app_ctrl & 0x80)
        fin = bool(app_ctrl & 0x40)
        con = bool(app_ctrl & 0x20)
        uns = bool(app_ctrl & 0x10)
        fields.append(
            _field(
                "app_control",
                "应用控制字",
                _user_wire_offset(user_data_start, app_offset),
                bytes([app_ctrl]),
                f"0x{app_ctrl:02X}",
                f"FIR={fir} FIN={fin} CON={con} UNS={uns} SEQ={seq}",
            )
        )
        if len(user_data) >= app_offset + 2:
            fc = user_data[app_offset + 1]
            fc_name = DNP3_FUNCTION_CODES.get(fc, f"未知0x{fc:02X}")
            fields.append(
                _field(
                    "function_code",
                    "功能码",
                    _user_wire_offset(user_data_start, app_offset + 1),
                    user_data[app_offset + 1 : app_offset + 2],
                    f"0x{fc:02X} {fc_name}",
                )
            )
            result["summary"] = fc_name
            result["application_sequence"] = seq
            result["application_function_code"] = fc
            result["application_function"] = fc_name
            result["purpose"] = "应用层请求/响应"
            result["frame_kind"] = "应用帧(请求)" if fc < _RESPONSE_FC_START else "应用帧(响应)"
            # IIN（响应帧才有）
            if fc >= _RESPONSE_FC_START and len(user_data) >= app_offset + 4:
                iin1, iin2 = user_data[app_offset + 2], user_data[app_offset + 3]
                iin_desc = _decoded_iin(iin1, iin2)
                fields.append(
                    _field(
                        "iin",
                        "内部指示(IIN)",
                        _user_wire_offset(user_data_start, app_offset + 2),
                        user_data[app_offset + 2 : app_offset + 4],
                        f"0x{iin1:02X}{iin2:02X}",
                        iin_desc,
                    )
                )

            object_offset = app_offset + (4 if fc >= _RESPONSE_FC_START else 2)
            if len(user_data) > object_offset:
                _parse_application_objects(
                    result,
                    bytes(user_data[object_offset:]),
                    user_data_start=user_data_start,
                    logical_base=object_offset,
                    function_code=fc,
                )
                _append_object_summary(result)

    if request_context:
        result["correlation"] = request_context
    return result


def _link_control_desc(ctrl: int) -> str:
    """将链路控制字解析为中文描述文本。"""
    primary = bool(ctrl & 0x40)
    function = ctrl & 0x0F
    parts = ["主站方向" if ctrl & 0x80 else "从站方向", f"PRM={int(primary)}"]
    if primary:
        parts.extend([f"FCB={int(bool(ctrl & 0x20))}", f"FCV={int(bool(ctrl & 0x10))}"])
        parts.append(_PRIMARY_LINK_FUNCTIONS.get(function, f"主站功能码0x{function:02X}"))
    else:
        parts.extend([f"DFC={int(bool(ctrl & 0x10))}"])
        parts.append(_SECONDARY_LINK_FUNCTIONS.get(function, f"从站功能码0x{function:02X}"))
    return " ".join(parts)


def _link_is_server_data(ctrl: int) -> bool:
    """判断控制字是否为从站方向、PRM=0 的确认数据帧。"""
    # 从站发出的数据帧（主站PRM=1，从站PRM=0）
    return (ctrl & 0x80) == 0 and (ctrl & 0x40) == 0 and (ctrl & 0x0F) == 3


def _has_transport_header(user_data: bytes | bytearray) -> bool:
    """兼容历史上直接把应用层数据放入链路帧的测试/抓包。"""
    if len(user_data) < 3:
        return False
    transport = user_data[0]
    app_control = user_data[1]
    function_code = user_data[2]
    return bool(transport & 0x80) and (app_control & 0xC0) == 0xC0 and function_code in _KNOWN_FUNCTION_CODES


def _user_wire_offset(user_data_start: int, logical_offset: int) -> int:
    """将去 CRC 后的用户数据偏移换算为原始链路帧偏移。"""
    return user_data_start + logical_offset + (logical_offset // 16) * 2


def _wire_span_length(logical_offset: int, logical_length: int) -> int:
    """返回一段用户数据在原始帧中占用的长度（包含中间的数据块 CRC）。"""
    if logical_length <= 0:
        return 0
    start = logical_offset + (logical_offset // 16) * 2
    end_offset = logical_offset + logical_length
    end = end_offset + ((end_offset - 1) // 16) * 2
    return end - start


def _parse_application_objects(
    result: dict[str, Any],
    payload: bytes,
    *,
    user_data_start: int,
    logical_base: int,
    function_code: int,
) -> None:
    """解析 DNP3 对象头，并把响应数据逐点转换成通用详情对象。"""
    try:
        from pydnp3_pure.app.object_header import parse_object_header
        from pydnp3_pure.objects import get_handler
        from pydnp3_pure.util.buffer import ReadBuffer

        import src.proto.dnp3.objects  # noqa: F401
    except ImportError:
        result["complete"] = False
        result["warnings"].append("DNP3对象解析组件不可用")
        return

    buffer = ReadBuffer(payload)
    while buffer.remaining > 0:
        header_start = buffer.offset
        try:
            header = parse_object_header(buffer)
        except (IndexError, ValueError, struct.error):
            result["complete"] = False
            result["warnings"].append("DNP3对象头不完整或限定词不受支持")
            break

        header_end = buffer.offset
        group_name = DNP3_OBJECT_GROUPS.get(header.group, "未知对象组")
        header_description = _object_header_description(header)
        header_logical_offset = logical_base + header_start
        header_raw = payload[header_start:header_end]
        result["fields"].append(
            _field(
                f"object_header_{len(result['objects'])}",
                f"对象头 G{header.group}V{header.variation}",
                _user_wire_offset(user_data_start, header_logical_offset),
                header_raw,
                header_description,
                group_name,
            )
        )

        if function_code in _SELECTOR_FUNCTION_CODES or header.count == 0:
            _append_selector_objects(
                result,
                header,
                header_raw,
                user_data_start=user_data_start,
                logical_offset=header_logical_offset,
                group_name=group_name,
            )
            continue

        handler = get_handler(header.group)
        if handler is None:
            result["complete"] = False
            result["warnings"].append(f"G{header.group}V{header.variation} 的对象值暂不支持解析")
            raw_start = buffer.offset
            next_header = _find_next_known_object(payload, raw_start + 1)
            raw_end = next_header if next_header is not None else len(payload)
            unknown_raw = payload[raw_start:raw_end]
            result["objects"].append(
                {
                    "index": len(result["objects"]),
                    "offset": _user_wire_offset(user_data_start, header_logical_offset),
                    "length": _wire_span_length(header_logical_offset, header_end - header_start + len(unknown_raw)),
                    "address": header.start if header.count == 1 else None,
                    "address_range": [header.start, header.stop] if header.count else None,
                    "value": "未知对象原始数据",
                    "raw_value": _hex(unknown_raw),
                    "raw_offset": raw_start,
                    "quality": None,
                    "timestamp": None,
                    "fields": [],
                    "name": f"G{header.group}V{header.variation} {group_name}",
                    "dnp3_group": header.group,
                    "dnp3_variation": header.variation,
                }
            )
            buffer.seek(raw_end)
            continue

        data_start = buffer.offset
        try:
            points = handler.parse(
                variation=header.variation,
                qualifier=header.qualifier,
                count=header.count,
                start=header.start,
                buf=buffer,
            )
        except (IndexError, ValueError, struct.error):
            result["complete"] = False
            result["warnings"].append(f"G{header.group}V{header.variation} 对象数据不完整或格式不支持")
            break
        data_end = buffer.offset
        if not points and header.count:
            result["complete"] = False
            result["warnings"].append(f"G{header.group}V{header.variation} 未解析出对象值")
            break
        _append_value_objects(
            result,
            payload,
            header,
            points,
            handler,
            data_start=data_start,
            data_end=data_end,
            user_data_start=user_data_start,
            logical_base=logical_base,
            group_name=group_name,
        )


def _find_next_known_object(payload: bytes, start: int) -> int | None:
    """Best-effort recovery after an unknown object while retaining its raw bytes."""
    from pydnp3_pure.app.object_header import parse_object_header
    from pydnp3_pure.objects import get_handler
    from pydnp3_pure.util.buffer import ReadBuffer

    for offset in range(start, len(payload) - 2):
        candidate = ReadBuffer(payload[offset:])
        try:
            header = parse_object_header(candidate)
            handler = get_handler(header.group)
            if handler is None or header.variation not in handler.supported_variations:
                continue
            handler.parse(header.variation, header.qualifier, header.count, header.start, candidate)
        except (IndexError, ValueError, struct.error):
            continue
        return offset
    return None


def _object_header_description(header: Any) -> str:
    """生成 DNP3 对象头的可读描述文本。"""
    qualifier_name = getattr(header.qualifier, "name", f"0x{int(header.qualifier):02X}")
    if header.count:
        if header.stop >= header.start:
            address = f"，地址 {header.start}～{header.stop}"
        else:
            address = ""
        return f"G{header.group}V{header.variation}，{qualifier_name}{address}，数量 {header.count}"
    return f"G{header.group}V{header.variation}，{qualifier_name}，全部点"


def _append_selector_objects(
    result: dict[str, Any],
    header: Any,
    header_raw: bytes,
    *,
    user_data_start: int,
    logical_offset: int,
    group_name: str,
) -> None:
    """将仅选择而无值的对象（如读请求）追加为通用详情对象。"""
    addresses: list[int | None]
    if int(header.qualifier) in (0x00, 0x01, 0x02) and header.count and header.stop >= header.start:
        addresses = list(range(header.start, header.stop + 1))
    else:
        addresses = [None]
    if len(addresses) > 4096:
        addresses = [None]
        result["warnings"].append("对象地址范围过大，详情中仅显示范围")

    for address in addresses:
        value = "全部点" if address is None else "对象选择"
        result["objects"].append(
            {
                "index": len(result["objects"]),
                "offset": _user_wire_offset(user_data_start, logical_offset),
                "length": _wire_span_length(logical_offset, len(header_raw)),
                "address": address,
                "value": value,
                "raw_value": _hex(header_raw),
                "quality": None,
                "timestamp": None,
                "fields": [],
                "name": f"G{header.group}V{header.variation} {group_name}",
                "dnp3_group": header.group,
                "dnp3_variation": header.variation,
                "address_range": [header.start, header.stop] if header.count else None,
            }
        )


def _append_value_objects(
    result: dict[str, Any],
    payload: bytes,
    header: Any,
    points: list[Any],
    handler: Any,
    *,
    data_start: int,
    data_end: int,
    user_data_start: int,
    logical_base: int,
    group_name: str,
) -> None:
    """将解析出的对象值按测点逐个追加为通用详情对象。"""
    point_size = handler.point_size(header.variation)
    prefix_size = header.index_size
    for ordinal, point in enumerate(points):
        if point_size < 0:
            point_start = data_start + ordinal // 8
            point_length = 1
            value_start = point_start
        else:
            point_length = prefix_size + point_size
            point_start = data_start + ordinal * point_length
            value_start = point_start + prefix_size
        point_end = min(point_start + point_length, data_end)
        raw_value = payload[value_start:point_end]
        logical_offset = logical_base + point_start
        address, value, flags, status, timestamp = _normalize_point(point, header.start + ordinal)
        quality = _decode_point_flags(flags) if flags is not None else None
        if status is not None:
            quality = {**(quality or {}), "status": status}
        timestamp_text = _format_timestamp(timestamp)
        point_fields = [
            _field(
                "object_address",
                "对象索引",
                _user_wire_offset(user_data_start, logical_offset),
                payload[point_start:value_start],
                address,
                "无索引前缀时由对象头起始地址递增",
            ),
            _field(
                "object_value",
                "对象值",
                _user_wire_offset(user_data_start, logical_base + value_start),
                raw_value,
                value,
            ),
        ]
        result["objects"].append(
            {
                "index": len(result["objects"]),
                "offset": _user_wire_offset(user_data_start, logical_offset),
                "length": _wire_span_length(logical_offset, max(point_end - point_start, 1)),
                "address": address,
                "value": value,
                "raw_value": _hex(raw_value),
                "quality": quality,
                "timestamp": timestamp_text,
                "fields": point_fields,
                "name": f"G{header.group}V{header.variation} {group_name}",
                "dnp3_group": header.group,
                "dnp3_variation": header.variation,
            }
        )


def _normalize_point(point: Any, default_index: int) -> tuple[int, Any, int | None, int | None, Any]:
    """将解析对象归一化为地址、值、品质、状态与时间戳。"""
    address = default_index
    value_source = point
    if isinstance(point, tuple) and len(point) == 2:
        address, value_source = point
    else:
        address = int(getattr(point, "index", default_index))

    flags = getattr(value_source, "flags", None)
    status = getattr(value_source, "status", None)
    timestamp = getattr(value_source, "timestamp", None)
    if hasattr(value_source, "value"):
        value: Any = value_source.value
    elif hasattr(value_source, "ms_since_epoch"):
        timestamp = value_source
        value = _format_timestamp(value_source)
    elif hasattr(value_source, "control"):
        value = {
            "control": value_source.control,
            "count": value_source.count,
            "on_time_ms": value_source.on_time_ms,
            "off_time_ms": value_source.off_time_ms,
        }
    else:
        value = value_source
    return (
        int(address),
        value,
        int(flags) if flags is not None else None,
        int(status) if status is not None else None,
        timestamp,
    )


def _decode_point_flags(flags: int) -> dict[str, Any]:
    """将品质标志位解码为布尔集合字典。"""
    return {
        "raw": f"0x{flags:02X}",
        "online": bool(flags & 0x01),
        "restart": bool(flags & 0x02),
        "communication_lost": bool(flags & 0x04),
        "remote_forced": bool(flags & 0x08),
        "local_forced": bool(flags & 0x10),
        "over_range_or_chatter": bool(flags & 0x20),
        "reference_error_or_discontinuity": bool(flags & 0x40),
    }


def _format_timestamp(timestamp: Any) -> str | None:
    """将时间戳对象统一格式化为 ISO 字符串。"""
    if timestamp is None:
        return None
    if hasattr(timestamp, "to_datetime"):
        timestamp = timestamp.to_datetime()
    if hasattr(timestamp, "isoformat"):
        return timestamp.isoformat(sep=" ", timespec="milliseconds")
    return str(timestamp)


def _append_object_summary(result: dict[str, Any]) -> None:
    """在解析结果摘要中追加对象组、地址范围等信息。"""
    objects = result["objects"]
    if not objects:
        return
    groups = list(dict.fromkeys(f"G{item['dnp3_group']}V{item['dnp3_variation']}" for item in objects))
    addresses = [item["address"] for item in objects if isinstance(item.get("address"), int)]
    suffix = f"，{','.join(groups)}"
    if addresses:
        if len(addresses) == 1:
            suffix += f"，地址 {addresses[0]}"
        elif addresses == list(range(addresses[0], addresses[-1] + 1)):
            suffix += f"，地址 {addresses[0]}～{addresses[-1]}"
        else:
            shown = "、".join(str(address) for address in addresses[:8])
            suffix += f"，地址 {shown}" + ("…" if len(addresses) > 8 else "")
    elif any(item.get("address_range") is None for item in objects):
        suffix += "，全部点"
    result["summary"] += suffix


def _decoded_iin(iin1: int, iin2: int) -> str:
    """将 IIN1/IIN2 字节解码为中文指示描述列表。"""
    flags = []
    if iin1 & 0x01:
        flags.append("收到全站广播")
    if iin1 & 0x02:
        flags.append("有1类事件")
    if iin1 & 0x04:
        flags.append("有2类事件")
    if iin1 & 0x08:
        flags.append("有3类事件")
    if iin1 & 0x10:
        flags.append("时间不同步")
    if iin1 & 0x20:
        flags.append("本地控制")
    if iin1 & 0x40:
        flags.append("设备故障")
    if iin1 & 0x80:
        flags.append("设备重启")
    if iin2 & 0x01:
        flags.append("功能码不支持")
    if iin2 & 0x02:
        flags.append("对象未知")
    if iin2 & 0x04:
        flags.append("参数错误")
    if iin2 & 0x08:
        flags.append("事件缓冲溢出")
    if iin2 & 0x10:
        flags.append("已在执行")
    if iin2 & 0x20:
        flags.append("配置损坏")
    return ", ".join(flags) if flags else "无特殊指示"
