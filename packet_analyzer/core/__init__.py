"""报文解析内核：协议注册、分帧、解析与记录仓库。"""

from .ifaces import Interface, capture_available, list_interfaces, local_addresses
from .pcap import FrameMeta, PcapCaptureEngine, PcapConfig, describe_bpf
from .registry import (
    AUTO,
    CHOICES,
    PROTOCOLS,
    ROLE_REQUEST,
    ROLE_RESPONSE,
    FrameSplitter,
    ProtocolSpec,
    describe,
    detect_protocol,
    frame_address,
    frame_length,
    is_known,
    parse_frame,
    spec_of,
)
from .store import FrameRecord, MessageStore, format_time

__all__ = [
    "AUTO",
    "CHOICES",
    "PROTOCOLS",
    "ROLE_REQUEST",
    "ROLE_RESPONSE",
    "FrameMeta",
    "FrameRecord",
    "FrameSplitter",
    "Interface",
    "MessageStore",
    "PcapCaptureEngine",
    "PcapConfig",
    "ProtocolSpec",
    "capture_available",
    "describe",
    "describe_bpf",
    "detect_protocol",
    "format_time",
    "frame_address",
    "frame_length",
    "is_known",
    "list_interfaces",
    "local_addresses",
    "parse_frame",
    "spec_of",
]
