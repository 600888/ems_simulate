"""链路层 → 传输层解析（无第三方依赖）。

从 pcap 拿到的原始帧按 ``pcap_datalink()`` 的类型分别处理：

===========  ==========================================================
DLT          帧结构
===========  ==========================================================
DLT_NULL_    4 字节地址族（本机字节序），随后是 IP 报文
DLT_EN10MB   以太网头 14 字节，可能有多层 VLAN 标签
DLT_RAW_     IP 报文直接开始
DLT_LINUX_SLL 16 字节"cooked"头，协议类型在偏移 14
===========  ==========================================================

只解析到 TCP/UDP 的头部与载荷，足够后续按协议分帧；
GOOSE 这类二层报文会原样带出以太网帧，交给 GOOSE 解析器处理。
"""

from __future__ import annotations

from dataclasses import dataclass

# 链路层类型（与 libpcap 的 pcap_datalink 返回值一致）
DLT_NULL = 0
DLT_EN10MB = 1
DLT_RAW_BSD = 12
DLT_RAW = 101
DLT_LINUX_SLL = 113
DLT_LINUX_SLL2 = 276

ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_IPV6 = 0x86DD
ETHERTYPE_GOOSE = 0x88B8
_VLAN_TYPES = (0x8100, 0x88A8, 0x9100)

IPPROTO_TCP = 6
IPPROTO_UDP = 17
# IPv6 扩展头：逐跳、路由、分片、目的选项
_IPV6_EXTENSIONS = (0, 43, 44, 60)
_IPV6_FRAGMENT = 44

_AF_INET = 2
_AF_INET6 = (10, 23, 28, 30)


@dataclass
class TransportSegment:
    """一帧解析出的传输层信息。"""

    src_ip: str = ""
    dst_ip: str = ""
    protocol: int = 0
    src_port: int = 0
    dst_port: int = 0
    seq: int = 0
    flags: int = 0
    payload: bytes = b""
    ethertype: int = 0
    goose_frame: bytes = b""

    @property
    def transport(self) -> str:
        if self.protocol == IPPROTO_TCP:
            return "TCP"
        if self.protocol == IPPROTO_UDP:
            return "UDP"
        return ""

    @property
    def is_goose(self) -> bool:
        return bool(self.goose_frame)

    @property
    def is_syn(self) -> bool:
        """TCP SYN 且非 ACK —— 用来识别连接发起方。"""
        return self.protocol == IPPROTO_TCP and bool(self.flags & 0x02) and not self.flags & 0x10


def _ipv4(text: bytes) -> str:
    return ".".join(str(byte) for byte in text)


def _ipv6(text: bytes) -> str:
    # 按 RFC 5952 输出：组内去前导零，最长连续全零压缩成 ::
    groups = [text[index : index + 2].hex().lstrip("0") or "0" for index in range(0, 16, 2)]
    best_start, best_len, run_start = -1, 0, -1
    for index, group in enumerate([*groups, "x"]):
        if group == "0":
            if run_start < 0:
                run_start = index
        elif run_start >= 0:
            if index - run_start > best_len:
                best_start, best_len = run_start, index - run_start
            run_start = -1
    if best_len >= 2:
        head = ":".join(groups[:best_start])
        tail = ":".join(groups[best_start + best_len :])
        return f"{head}::{tail}"
    return ":".join(groups)


def _parse_ipv4(data: bytes) -> TransportSegment | None:
    if len(data) < 20:
        return None
    ihl = (data[0] & 0x0F) * 4
    if ihl < 20 or len(data) < ihl:
        return None
    total = int.from_bytes(data[2:4], "big")
    if 0 < total <= len(data):
        data = data[:total]
    # 非首片分片没有完整传输层头，跳过（重组交给后续解析器）
    if int.from_bytes(data[6:8], "big") & 0x1FFF:
        return None
    protocol = data[9]
    return _parse_transport(
        segment=TransportSegment(
            src_ip=_ipv4(data[12:16]),
            dst_ip=_ipv4(data[16:20]),
            protocol=protocol,
            ethertype=ETHERTYPE_IPV4,
        ),
        data=data[ihl:],
    )


def _parse_ipv6(data: bytes) -> TransportSegment | None:
    if len(data) < 40:
        return None
    protocol = data[6]
    payload = data[40:]
    declared = int.from_bytes(data[4:6], "big")
    if 0 < declared <= len(payload):
        payload = payload[:declared]
    # 逐层跳过扩展头，直到传输层协议
    guard = 0
    while protocol in _IPV6_EXTENSIONS and payload and guard < 8:
        if protocol == _IPV6_FRAGMENT:
            return None  # 分片报文不在这里重组
        if len(payload) < 2:
            return None
        protocol, length = payload[0], (payload[1] + 1) * 8
        if length < 8 or len(payload) < length:
            return None
        payload = payload[length:]
        guard += 1
    return _parse_transport(
        segment=TransportSegment(
            src_ip=_ipv6(data[8:24]),
            dst_ip=_ipv6(data[24:40]),
            protocol=protocol,
            ethertype=ETHERTYPE_IPV6,
        ),
        data=payload,
    )


def _parse_transport(*, segment: TransportSegment, data: bytes) -> TransportSegment | None:
    if segment.protocol == IPPROTO_TCP:
        if len(data) < 20:
            return None
        header_length = (data[12] >> 4) * 4
        if header_length < 20 or len(data) < header_length:
            return None
        segment.src_port = int.from_bytes(data[0:2], "big")
        segment.dst_port = int.from_bytes(data[2:4], "big")
        segment.seq = int.from_bytes(data[4:8], "big")
        segment.flags = data[13]
        segment.payload = data[header_length:]
        return segment
    if segment.protocol == IPPROTO_UDP:
        if len(data) < 8:
            return None
        segment.src_port = int.from_bytes(data[0:2], "big")
        segment.dst_port = int.from_bytes(data[2:4], "big")
        declared = int.from_bytes(data[4:6], "big")
        body = data[8:]
        segment.payload = body[: declared - 8] if 8 < declared <= len(data) else body
        return segment
    return None


def parse_link_frame(raw: bytes, datalink: int) -> TransportSegment | None:
    """把一帧原始报文（含链路层头）解析成传输层信息。"""
    if len(raw) < 4:
        return None

    if datalink == DLT_EN10MB:
        return _parse_ethernet(raw)
    if datalink == DLT_NULL:
        # 4 字节地址族，Windows 为小端，macOS 为大端
        family = int.from_bytes(raw[:4], "little")
        if family not in (_AF_INET, *_AF_INET6):
            family = int.from_bytes(raw[:4], "big")
        body = raw[4:]
        if family == _AF_INET:
            return _parse_ipv4(body)
        if family in _AF_INET6:
            return _parse_ipv6(body)
        return None
    if datalink in (DLT_RAW, DLT_RAW_BSD):
        version = raw[0] >> 4
        if version == 4:
            return _parse_ipv4(raw)
        if version == 6:
            return _parse_ipv6(raw)
        return None
    if datalink == DLT_LINUX_SLL:
        if len(raw) < 16:
            return None
        ethertype = int.from_bytes(raw[14:16], "big")
        return _dispatch_ethertype(ethertype, raw[16:], raw)
    if datalink == DLT_LINUX_SLL2:
        if len(raw) < 20:
            return None
        ethertype = int.from_bytes(raw[0:2], "big")
        return _dispatch_ethertype(ethertype, raw[20:], raw)
    # 未知链路类型：退化为按 IP 版本猜测
    version = raw[0] >> 4
    if version == 4:
        return _parse_ipv4(raw)
    if version == 6:
        return _parse_ipv6(raw)
    return None


def _parse_ethernet(raw: bytes) -> TransportSegment | None:
    if len(raw) < 14:
        return None
    ethertype = int.from_bytes(raw[12:14], "big")
    offset = 14
    # 逐层跳过 VLAN 标签（QinQ 会出现两层）
    while ethertype in _VLAN_TYPES and len(raw) >= offset + 4:
        ethertype = int.from_bytes(raw[offset + 2 : offset + 4], "big")
        offset += 4
    return _dispatch_ethertype(ethertype, raw[offset:], raw)


def _dispatch_ethertype(ethertype: int, body: bytes, raw: bytes) -> TransportSegment | None:
    if ethertype == ETHERTYPE_IPV4:
        return _parse_ipv4(body)
    if ethertype == ETHERTYPE_IPV6:
        return _parse_ipv6(body)
    if ethertype == ETHERTYPE_GOOSE:
        # GOOSE 是二层报文，把完整以太网帧带出去交给 GOOSE 解析器
        return TransportSegment(ethertype=ETHERTYPE_GOOSE, goose_frame=bytes(raw))
    return None
