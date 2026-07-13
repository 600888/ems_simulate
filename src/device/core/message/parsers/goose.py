"""Field-level IEC 61850 GOOSE Ethernet/BER parser."""

from __future__ import annotations

import struct
from typing import Any

from .common import _fail, _field, _hex, _result, _validation

ETHER_TYPE_GOOSE = 0x88B8
ETHER_TYPE_VLAN = 0x8100

PDU_FIELDS = {
    0x80: ("go_cb_ref", "GoCB引用", "string"),
    0x81: ("time_allowed_to_live", "允许生存时间", "integer"),
    0x82: ("data_set_ref", "DataSet引用", "string"),
    0x83: ("go_id", "GoID", "string"),
    0x84: ("goose_timestamp", "事件时间", "utc_time"),
    0x85: ("st_num", "状态号stNum", "integer"),
    0x86: ("sq_num", "序列号sqNum", "integer"),
    0x87: ("simulation", "仿真标志", "boolean"),
    0x88: ("conf_rev", "配置版本confRev", "integer"),
    0x89: ("nds_com", "调试标志ndsCom", "boolean"),
    0x8A: ("num_entries", "DataSet条目数", "integer"),
}

MMS_TYPES = {
    0x83: "boolean",
    0x84: "bitstring",
    0x85: "integer",
    0x86: "unsigned",
    0x87: "float",
    0x89: "octet_string",
    0x8A: "string",
    0x91: "timestamp",
}


def _read_length(data: bytes, offset: int) -> tuple[int | None, int]:
    if offset >= len(data):
        return None, offset
    first = data[offset]
    offset += 1
    if not first & 0x80:
        return first, offset
    count = first & 0x7F
    if count == 0 or offset + count > len(data):
        return None, offset
    return int.from_bytes(data[offset : offset + count], "big"), offset + count


def _decode_utc_time(raw: bytes) -> dict[str, Any] | str:
    if len(raw) != 8:
        return _hex(raw)
    seconds = int.from_bytes(raw[:4], "big")
    fraction = int.from_bytes(raw[4:7], "big") / 0x1000000
    return {
        "unix_seconds": seconds,
        "fraction": round(fraction, 9),
        "quality": f"0x{raw[7]:02X}",
    }


def _decode_mms(tag: int, raw: bytes) -> Any:
    if tag == 0x83:
        return bool(raw[0]) if raw else False
    if tag == 0x84:
        return int.from_bytes(raw[1:], "big") if len(raw) > 1 else 0
    if tag == 0x85:
        return int.from_bytes(raw, "big", signed=True) if raw else 0
    if tag == 0x86:
        return int.from_bytes(raw, "big") if raw else 0
    if tag == 0x87:
        payload = raw[1:] if len(raw) in (5, 9) else raw
        if len(payload) == 4:
            return round(struct.unpack(">f", payload)[0], 6)
        if len(payload) == 8:
            return round(struct.unpack(">d", payload)[0], 9)
        return _hex(raw)
    if tag == 0x89:
        return raw.hex()
    if tag == 0x8A:
        return raw.decode("utf-8", errors="replace")
    if tag == 0x91:
        return _decode_utc_time(raw)
    return raw.hex()


def _parse_all_data(result: dict[str, Any], data: bytes, start: int, end: int) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    cursor = start
    while cursor < end:
        object_start = cursor
        tag = data[cursor]
        cursor += 1
        length, value_start = _read_length(data, cursor)
        if length is None or value_start + length > end:
            result["complete"] = False
            result["warnings"].append(f"ALL_DATA第{len(objects)}项BER长度无效")
            break
        value_end = value_start + length
        raw_value = data[value_start:value_end]
        objects.append(
            {
                "index": len(objects),
                "offset": object_start,
                "length": value_end - object_start,
                "value_offset": value_start,
                "value_length": length,
                "address": None,
                "type": MMS_TYPES.get(tag, f"unknown(0x{tag:02X})"),
                "ber_tag": f"0x{tag:02X}",
                "value": _decode_mms(tag, raw_value),
                "raw_value": _hex(data[object_start:value_end]),
                "value_raw_hex": _hex(raw_value),
                "quality": None,
                "timestamp": None,
                "fields": [
                    _field("value", "DataSet值", value_start, raw_value, _decode_mms(tag, raw_value)),
                ],
            }
        )
        cursor = value_end
    return objects


def parse_goose(raw: bytes, *, role: str = "Publish") -> dict[str, Any]:
    result = _result("IEC 61850 GOOSE", raw)
    result["role"] = role.lower()
    if len(raw) < 22:
        return _fail(result, "GOOSE以太网帧长度不足22字节")

    fields = result["fields"]
    dst_mac = ":".join(f"{byte:02X}" for byte in raw[:6])
    src_mac = ":".join(f"{byte:02X}" for byte in raw[6:12])
    ether_type = int.from_bytes(raw[12:14], "big")
    fields.extend(
        [
            _field("dst_mac", "目的MAC", 0, raw[:6], dst_mac),
            _field("src_mac", "源MAC", 6, raw[6:12], src_mac),
            _field("ether_type", "以太网类型", 12, raw[12:14], f"0x{ether_type:04X}"),
        ]
    )
    header_offset = 14
    result.update(src_mac=src_mac, dst_mac=dst_mac, has_vlan=False, vlan_id=0, vlan_prio=0)
    if ether_type == ETHER_TYPE_VLAN:
        if len(raw) < 26:
            return _fail(result, "带VLAN的GOOSE帧长度不足")
        tci = int.from_bytes(raw[14:16], "big")
        ether_type = int.from_bytes(raw[16:18], "big")
        result.update(has_vlan=True, vlan_id=tci & 0x0FFF, vlan_prio=(tci >> 13) & 0x07)
        fields.extend(
            [
                _field("vlan_tci", "VLAN TCI", 14, raw[14:16], f"VID={result['vlan_id']}, P={result['vlan_prio']}"),
                _field("ether_type", "VLAN内层类型", 16, raw[16:18], f"0x{ether_type:04X}"),
            ]
        )
        header_offset = 18
    if ether_type != ETHER_TYPE_GOOSE:
        return _fail(result, f"以太网类型0x{ether_type:04X}不是GOOSE")

    app_id = int.from_bytes(raw[header_offset : header_offset + 2], "big")
    declared_length = int.from_bytes(raw[header_offset + 2 : header_offset + 4], "big")
    fields.extend(
        [
            _field("app_id", "APPID", header_offset, raw[header_offset : header_offset + 2], f"0x{app_id:04X}"),
            _field(
                "goose_length",
                "GOOSE长度",
                header_offset + 2,
                raw[header_offset + 2 : header_offset + 4],
                declared_length,
            ),
            _field(
                "reserved1",
                "保留字段1",
                header_offset + 4,
                raw[header_offset + 4 : header_offset + 6],
                f"0x{int.from_bytes(raw[header_offset + 4 : header_offset + 6], 'big'):04X}",
            ),
            _field(
                "reserved2",
                "保留字段2",
                header_offset + 6,
                raw[header_offset + 6 : header_offset + 8],
                f"0x{int.from_bytes(raw[header_offset + 6 : header_offset + 8], 'big'):04X}",
            ),
        ]
    )
    _validation(
        result,
        "GOOSE长度",
        declared_length == len(raw) - header_offset,
        f"声明{declared_length}字节，实际{len(raw) - header_offset}字节",
    )
    result["app_id"] = app_id
    pdu_start = header_offset + 8
    if raw[pdu_start] != 0x61:
        return _fail(result, f"GOOSE PDU标签应为0x61，实际0x{raw[pdu_start]:02X}")
    pdu_length, content_start = _read_length(raw, pdu_start + 1)
    if pdu_length is None:
        return _fail(result, "GOOSE PDU BER长度无效")
    pdu_end = min(content_start + pdu_length, len(raw))
    fields.append(_field("goose_pdu", "GOOSE PDU", pdu_start, raw[pdu_start:content_start], f"内容长度{pdu_length}"))
    cursor = content_start
    while cursor < pdu_end:
        tlv_start = cursor
        tag = raw[cursor]
        cursor += 1
        length, value_start = _read_length(raw, cursor)
        if length is None or value_start + length > pdu_end:
            result["complete"] = False
            result["warnings"].append(f"PDU字段0x{tag:02X}长度无效")
            break
        value_end = value_start + length
        value_raw = raw[value_start:value_end]
        if tag == 0xAB:
            fields.append(_field("all_data", "ALL_DATA", tlv_start, raw[tlv_start:value_start], f"{length}字节"))
            result["objects"] = _parse_all_data(result, raw, value_start, value_end)
        else:
            key, name, kind = PDU_FIELDS.get(tag, (f"tag_{tag:02x}", f"未知字段0x{tag:02X}", "raw"))
            if kind == "string":
                value: Any = value_raw.decode("utf-8", errors="replace")
            elif kind == "integer":
                value = int.from_bytes(value_raw, "big")
            elif kind == "boolean":
                value = bool(value_raw[0]) if value_raw else False
            elif kind == "utc_time":
                value = _decode_utc_time(value_raw)
            else:
                value = _hex(value_raw)
            result[key] = value
            fields.append(_field(key, name, tlv_start, raw[tlv_start:value_end], value, f"BER标签0x{tag:02X}"))
        cursor = value_end

    result["frame_kind"] = "GOOSE发布报文"
    result["summary"] = (
        f"APPID 0x{app_id:04X}，GoCB {result.get('go_cb_ref', '-') or '-'}，"
        f"stNum={result.get('st_num', 0)}，sqNum={result.get('sq_num', 0)}，"
        f"{len(result['objects'])}个DataSet值"
    )
    result["purpose"] = "发布DataSet状态变化或重传当前状态"
    return result
