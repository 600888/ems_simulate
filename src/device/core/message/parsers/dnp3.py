"""DNP3 (IEEE 1815) 报文解析器：链路层 / 传输层 / 应用层逐字段解析。"""

from __future__ import annotations

from typing import Any

from .common import _fail, _field, _result, _validation

DNP3_LINK_CONTROL = {
    0x00: "确认 - 主->从 (ACK)",
    0x01: "确认 - 主<-从",
    0x10: "请求复位远程链路 (RESET_LINK)",
    0x13: "请求链路状态 (TEST_LINK)",
    0x81: "确认从站 (CONFIRMED_USER_DATA P)",
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
    8: "冻结-清除 (Freeze, Clear)",
    9: "冻结-无确认 (Freeze, No Ack)",
    13: "冷重启 (Cold Restart)",
    14: "热重启 (Warm Restart)",
    20: "使能未请求上报 (Enable Unsolicited)",
    21: "禁止未请求上报 (Disable Unsolicited)",
    22: "分配类 (Assign Class)",
    23: "延迟测量 (Delay Measure)",
    129: "响应：成功",
    130: "响应：不支持文件",
    131: "响应：无对象",
    132: "响应：对象无效",
    133: "响应：文件不存在",
    134: "响应：不支持对象",
    135: "响应：文件被占用",
    136: "响应：超出文件大小",
    137: "响应：对象不能写入",
    138: "响应：文件错误",
}

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
    user_data_raw = raw[user_data_start:] if length > header_payload_len else b""

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
    if user_data_raw:
        pos = 0
        block_idx = 0
        while pos < len(user_data_raw):
            block_payload = user_data_raw[pos : pos + 16]
            block_data_len = min(len(block_payload) - 2, 16) if len(block_payload) >= 2 else len(block_payload)
            if not _check_crc_block(user_data_raw, pos, block_data_len):
                block_errors.append(f"块{block_idx} CRC错")
            pos += block_data_len + 2
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
    while pos < len(user_data_raw):
        chunk = user_data_raw[pos : pos + 16]
        real = min(len(chunk) - 2, 16) if len(chunk) >= 2 else len(chunk)
        user_data.extend(chunk[:real])
        pos += real + 2

    result["frame_kind"] = "链路数据帧"
    result["purpose"] = "从站→主站数据" if _link_is_server_data(ctrl) else "链路层数据帧"

    # ---- 应用层 ----
    if len(user_data) >= 1:
        app_ctrl = user_data[0]
        seq = app_ctrl & 0x0F
        fir = bool(app_ctrl & 0x80)
        fin = bool(app_ctrl & 0x40)
        con = bool(app_ctrl & 0x20)
        uns = bool(app_ctrl & 0x10)
        fields.append(
            _field(
                "app_control",
                "应用控制字",
                user_data_start,
                bytes([app_ctrl]),
                f"0x{app_ctrl:02X}",
                f"FIR={fir} FIN={fin} CON={con} UNS={uns} SEQ={seq}",
            )
        )
        if len(user_data) >= 2:
            fc = user_data[1]
            fc_name = DNP3_FUNCTION_CODES.get(fc, f"未知0x{fc:02X}")
            fields.append(
                _field("function_code", "功能码", user_data_start + 1, user_data[1:2], f"0x{fc:02X} {fc_name}")
            )
            result["summary"] = fc_name
            result["purpose"] = "应用层请求/响应"
            result["frame_kind"] = "应用帧(请求)" if fc < _RESPONSE_FC_START else "应用帧(响应)"
            # IIN（响应帧才有）
            if fc >= _RESPONSE_FC_START and len(user_data) >= 4:
                iin1, iin2 = user_data[2], user_data[3]
                iin_desc = _decoded_iin(iin1, iin2)
                fields.append(
                    _field(
                        "iin", "内部指示(IIN)", user_data_start + 2, user_data[2:4], f"0x{iin1:02X}{iin2:02X}", iin_desc
                    )
                )

    if request_context:
        result["correlation"] = request_context
    return result


def _link_control_desc(ctrl: int) -> str:
    parts = []
    if ctrl & 0x80:
        parts.append("主站")
    else:
        parts.append("从站")
    if ctrl & 0x40:
        parts.append("PRM")
    parts.append(DNP3_LINK_CONTROL.get(ctrl & 0xFF, f"功能码0x{ctrl & 0x0F:02X}"))
    return " ".join(parts)


def _link_is_server_data(ctrl: int) -> bool:
    # 从站发出的数据帧（主站PRM=1，从站PRM=0）
    return (ctrl & 0x80) == 0 and (ctrl & 0x40) == 0 and (ctrl & 0x0F) == 3


def _decoded_iin(iin1: int, iin2: int) -> str:
    flags = []
    if iin1 & 0x01:
        flags.append("设备重启")
    if iin1 & 0x04:
        flags.append("功能码不支持")
    if iin1 & 0x08:
        flags.append("对象未知")
    if iin2 & 0x01:
        flags.append("事件缓冲溢出")
    if iin2 & 0x04:
        flags.append("时间不同步")
    return ", ".join(flags) if flags else "无特殊指示"
