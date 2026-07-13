"""Field-level IEC 61850 MMS / RFC 1006 parser."""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any

from .common import _fail, _field, _hex, _result, _validation

MMS_PDUS = {
    0: "Confirmed-RequestPDU",
    1: "Confirmed-ResponsePDU",
    2: "Confirmed-ErrorPDU",
    3: "Unconfirmed-PDU",
    4: "RejectPDU",
    8: "Initiate-RequestPDU",
    9: "Initiate-ResponsePDU",
    10: "Initiate-ErrorPDU",
    11: "Conclude-RequestPDU",
    12: "Conclude-ResponsePDU",
    13: "Conclude-ErrorPDU",
}

MMS_SERVICES = {
    0: "Status",
    1: "GetNameList",
    2: "Identify",
    3: "Rename",
    4: "Read",
    5: "Write",
    6: "GetVariableAccessAttributes",
    7: "DefineNamedVariable",
    8: "DefineScatteredAccess",
    9: "GetScatteredAccessAttributes",
    10: "DeleteVariableAccess",
    11: "DefineNamedVariableList",
    12: "GetNamedVariableListAttributes",
    13: "DeleteNamedVariableList",
    14: "DefineNamedType",
    15: "GetNamedTypeAttributes",
    16: "DeleteNamedType",
    17: "Input",
    18: "Output",
    19: "TakeControl",
    20: "RelinquishControl",
    23: "ReportSemaphoreStatus",
    26: "InitiateDownloadSequence",
    27: "DownloadSegment",
    28: "TerminateDownloadSequence",
    29: "InitiateUploadSequence",
    30: "UploadSegment",
    31: "TerminateUploadSequence",
    32: "RequestDomainDownload",
    33: "RequestDomainUpload",
    34: "LoadDomainContent",
    35: "StoreDomainContent",
    36: "DeleteDomain",
    37: "GetDomainAttributes",
    38: "CreateProgramInvocation",
    39: "DeleteProgramInvocation",
    40: "Start",
    41: "Stop",
    42: "Resume",
    43: "Reset",
    44: "Kill",
    45: "GetProgramInvocationAttributes",
    46: "ObtainFile",
    47: "DefineEventCondition",
    48: "DeleteEventCondition",
    49: "GetEventConditionAttributes",
    50: "ReportEventConditionStatus",
    51: "AlterEventConditionMonitoring",
    52: "TriggerEvent",
    53: "DefineEventAction",
    54: "DeleteEventAction",
    55: "GetEventActionAttributes",
    56: "ReportEventActionStatus",
    57: "DefineEventEnrollment",
    58: "DeleteEventEnrollment",
    59: "AlterEventEnrollment",
    60: "ReportEventEnrollmentStatus",
    61: "GetEventEnrollmentAttributes",
    62: "AcknowledgeEventNotification",
    63: "GetAlarmSummary",
    64: "GetAlarmEnrollmentSummary",
    65: "ReadJournal",
    66: "WriteJournal",
    67: "InitializeJournal",
    68: "ReportJournalStatus",
    69: "CreateJournal",
    70: "DeleteJournal",
    71: "GetCapabilityList",
    72: "FileOpen",
    73: "FileRead",
    74: "FileClose",
    75: "FileRename",
    76: "FileDelete",
    77: "FileDirectory",
}

UNCONFIRMED_SERVICES = {0: "InformationReport", 1: "UnsolicitedStatus", 2: "EventNotification"}


@dataclass(frozen=True)
class BerNode:
    tag_class: int
    constructed: bool
    tag: int
    offset: int
    header_length: int
    length: int
    children: tuple[BerNode, ...] = ()

    @property
    def value_offset(self) -> int:
        return self.offset + self.header_length

    @property
    def end(self) -> int:
        return self.value_offset + self.length


def _read_tag(data: bytes, offset: int) -> tuple[int, bool, int, int]:
    first = data[offset]
    tag_class, constructed, tag, used = first >> 6, bool(first & 0x20), first & 0x1F, 1
    if tag == 0x1F:
        tag = 0
        while offset + used < len(data):
            byte = data[offset + used]
            used += 1
            tag = (tag << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
    return tag_class, constructed, tag, used


def _read_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    if first < 0x80:
        return first, 1
    count = first & 0x7F
    if count == 0 or count > 4 or offset + 1 + count > len(data):
        raise ValueError("不支持的BER长度编码")
    return int.from_bytes(data[offset + 1 : offset + 1 + count], "big"), count + 1


def _parse_node(data: bytes, offset: int, limit: int, depth: int = 0) -> BerNode:
    if offset >= limit or depth > 32:
        raise ValueError("BER结构不完整")
    tag_class, constructed, tag, tag_len = _read_tag(data, offset)
    length, len_len = _read_length(data, offset + tag_len)
    header = tag_len + len_len
    end = offset + header + length
    if end > limit:
        raise ValueError("BER声明长度超出报文")
    children: list[BerNode] = []
    if constructed:
        cursor = offset + header
        while cursor < end:
            child = _parse_node(data, cursor, end, depth + 1)
            children.append(child)
            cursor = child.end
    return BerNode(tag_class, constructed, tag, offset, header, length, tuple(children))


def _walk(node: BerNode):
    yield node
    for child in node.children:
        yield from _walk(child)


def _find_mms_node(roots: list[BerNode]) -> BerNode | None:
    confirmed: list[BerNode] = []
    association: list[BerNode] = []
    unconfirmed: list[BerNode] = []
    for root in roots:
        for node in _walk(root):
            if node.tag_class != 2 or node.tag not in MMS_PDUS:
                continue
            # Confirmed PDU begins with the universal INTEGER invoke ID. This
            # avoids mistaking ACSE's many context-specific A0/A1 fields for MMS.
            invalid_confirmed = not node.children or node.children[0].tag_class != 0 or node.children[0].tag != 2
            if node.tag in (0, 1, 2) and invalid_confirmed:
                continue
            if node.tag in (0, 1, 2):
                confirmed.append(node)
            elif node.tag in (8, 9, 10, 11, 12, 13):
                association.append(node)
            elif node.tag == 3 and node.constructed and node.children:
                first = node.children[0]
                if first.tag_class == 2 and first.tag in UNCONFIRMED_SERVICES:
                    unconfirmed.append(node)
    # Service choices inside a confirmed PDU reuse the same context tag numbers
    # as top-level MMS PDUs. Prefer the invoke-ID-bearing outer PDU and, among
    # duplicate roots found by scanning, the widest node.
    candidates = confirmed or association or unconfirmed
    return max(candidates, key=lambda item: item.end - item.offset) if candidates else None


def _integer(data: bytes) -> int:
    return int.from_bytes(data, "big", signed=bool(data and data[0] & 0x80))


def _decode_data_value(tag: int, value: bytes) -> tuple[str, Any] | None:
    if tag == 3:
        return "Boolean", bool(value and value[-1])
    if tag == 4:
        unused = value[0] if value else 0
        bits = "".join(f"{byte:08b}" for byte in value[1:])
        return "BitString", bits[: len(bits) - unused] if unused else bits
    if tag == 5:
        return "Integer", _integer(value)
    if tag == 6:
        return "Unsigned", int.from_bytes(value, "big")
    if tag == 7 and len(value) >= 5:
        if len(value) >= 9:
            return "FloatingPoint", struct.unpack(">d", value[1:9])[0]
        return "FloatingPoint", struct.unpack(">f", value[1:5])[0]
    if tag == 9:
        return "OctetString", _hex(value)
    if tag == 10:
        return "VisibleString", value.decode("ascii", errors="replace")
    if tag == 13:
        return "BCD", int.from_bytes(value, "big")
    if tag == 16:
        return "MMSString", value.decode("utf-8", errors="replace")
    if tag == 17 and len(value) == 8:
        seconds = int.from_bytes(value[:4], "big")
        fraction = int.from_bytes(value[4:7], "big") / 2**24
        return "UtcTime", round(seconds + fraction, 6)
    return None


def parse_mms(raw: bytes, *, role: str) -> dict[str, Any]:
    result = _result("IEC 61850 MMS", raw)
    result["role"] = role.lower()
    if len(raw) < 7 or raw[:2] != b"\x03\x00":
        return _fail(result, "MMS报文缺少有效TPKT头")

    declared = int.from_bytes(raw[2:4], "big")
    result["fields"].extend(
        [
            _field("tpkt_version", "TPKT版本", 0, raw[:1], raw[0], "RFC 1006版本，应为3"),
            _field("tpkt_reserved", "TPKT保留字段", 1, raw[1:2], raw[1]),
            _field("tpkt_length", "TPKT长度", 2, raw[2:4], declared, "包含4字节TPKT头"),
        ]
    )
    _validation(result, "TPKT长度", declared == len(raw), f"声明{declared}字节，实际{len(raw)}字节")

    cotp_length = raw[4]
    cotp_end = min(len(raw), 5 + cotp_length)
    if cotp_end <= 5:
        return _fail(result, "COTP头不完整")
    cotp_type = raw[5] & 0xF0
    cotp_names = {
        0xE0: "连接请求(CR)",
        0xD0: "连接确认(CC)",
        0x80: "断开请求(DR)",
        0xC0: "断开确认(DC)",
        0xF0: "数据传输(DT)",
    }
    cotp_name = cotp_names.get(cotp_type, f"未知COTP 0x{raw[5]:02X}")
    result["fields"].extend(
        [
            _field("cotp_length", "COTP头长度", 4, raw[4:5], cotp_length),
            _field("cotp_type", "COTP类型", 5, raw[5:6], cotp_name),
        ]
    )
    if cotp_type != 0xF0:
        result.update(frame_kind="COTP连接管理", summary=cotp_name, purpose="建立或释放OSI传输连接")
        return result
    if cotp_length >= 2 and len(raw) > 6:
        result["fields"].append(_field("cotp_eot", "COTP EOT", 6, raw[6:7], bool(raw[6] & 0x80), "TPDU结束标志"))

    payload_offset = 5 + cotp_length
    # Session and presentation headers contain non-BER SPDU bytes. Scan for
    # self-contained BER roots and let the MMS shape checks reject false hits.
    roots: list[BerNode] = []
    for cursor in range(payload_offset, len(raw)):
        # Top-level MMS choices and ACSE association PDUs use these single-byte
        # tags. Avoid attempting a recursive BER parse at every payload byte.
        if raw[cursor] not in (0x60, 0x61, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA8, 0xA9, 0xAA, 0x8B, 0x8C, 0x8D):
            continue
        try:
            roots.append(_parse_node(raw, cursor, len(raw)))
        except (IndexError, ValueError):
            continue

    mms = _find_mms_node(roots)
    if mms is None:
        acse = next(
            (node for root in roots for node in _walk(root) if node.tag_class == 1 and node.tag in (0, 1)),
            None,
        )
        if acse is not None:
            kind = "ACSE关联请求(AARQ)" if acse.tag == 0 else "ACSE关联响应(AARE)"
            result.update(frame_kind=kind, summary=kind, purpose="建立MMS应用关联")
        else:
            result.update(frame_kind="OSI会话/表示层报文", summary="OSI会话或表示层控制报文", purpose="管理MMS会话")
        return result

    pdu_name = MMS_PDUS[mms.tag]
    result["fields"].append(
        _field(
            "mms_pdu",
            "MMS PDU",
            mms.offset,
            raw[mms.offset : mms.offset + mms.header_length],
            pdu_name,
        )
    )
    invoke_id: int | None = None
    service_name = ""
    service_node: BerNode | None = None
    if mms.tag in (0, 1, 2) and mms.children:
        invoke_node = mms.children[0]
        invoke_raw = raw[invoke_node.value_offset : invoke_node.end]
        invoke_id = _integer(invoke_raw)
        result["fields"].append(
            _field(
                "invoke_id",
                "调用标识Invoke ID",
                invoke_node.offset,
                raw[invoke_node.offset : invoke_node.end],
                invoke_id,
                "匹配请求与响应",
            )
        )
        service_node = next((node for node in mms.children[1:] if node.tag_class == 2), None)
    elif mms.tag == 3:
        service_node = next((node for node in mms.children if node.tag_class == 2), None)

    if service_node is not None:
        services = UNCONFIRMED_SERVICES if mms.tag == 3 else MMS_SERVICES
        service_name = services.get(service_node.tag, f"Service[{service_node.tag}]")
        result["fields"].append(
            _field(
                "mms_service",
                "MMS服务",
                service_node.offset,
                raw[service_node.offset : service_node.offset + service_node.header_length],
                service_name,
            )
        )
        for node in _walk(service_node):
            if node.constructed or node.tag_class != 2:
                continue
            decoded = _decode_data_value(node.tag, raw[node.value_offset : node.end])
            if decoded is None:
                continue
            type_name, value = decoded
            result["objects"].append(
                {
                    "index": len(result["objects"]),
                    "offset": node.offset,
                    "length": node.end - node.offset,
                    "address": None,
                    "name": type_name,
                    "value": value,
                    "raw_value": _hex(raw[node.value_offset : node.end]),
                    "quality": None,
                    "timestamp": None,
                    "fields": [],
                }
            )

    qualifier = f"，Invoke ID={invoke_id}" if invoke_id is not None else ""
    service_text = f"，{service_name}" if service_name else ""
    result.update(
        frame_kind=pdu_name,
        summary=f"{pdu_name}{service_text}{qualifier}",
        purpose=service_name or pdu_name,
    )
    return result


def describe_mms(raw: bytes, *, role: str = "") -> str:
    detail = parse_mms(raw, role=role)
    return detail["summary"]
