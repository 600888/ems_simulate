"""协议注册表：协议元信息、自动识别、流式分帧与解析分发。

本模块是独立程序的核心入口，不依赖原项目的任何模块。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import struct
from typing import Any

from .dlt645 import parse_dlt645
from .dnp3 import _crc16_dnp3, parse_dnp3
from .ft12 import FT12Codec, FT12Error
from .goose import parse_goose
from .iec101 import parse_iec101
from .iec104 import IEC_TYPES, parse_iec104
from .mms import parse_mms
from .modbus import MODBUS_FUNCTIONS, _crc16_modbus, parse_modbus

AUTO = "auto"

# 解析方向：请求 / 响应
ROLE_REQUEST = "Request"
ROLE_RESPONSE = "Response"


@dataclass(frozen=True)
class ProtocolSpec:
    """一种协议的静态描述。"""

    key: str
    name: str
    short: str
    family: str
    role_labels: tuple[str, str]
    address_label: str
    stream: bool
    parse: Callable[..., dict[str, Any]]
    summary_of: Callable[[dict[str, Any]], str]


def _summary(detail: dict[str, Any]) -> str:
    return str(detail.get("summary") or "")


def _role_of(detail: dict[str, Any]) -> str:
    return str(detail.get("frame_kind") or "")


PROTOCOLS: dict[str, ProtocolSpec] = {
    "modbus_tcp": ProtocolSpec(
        key="modbus_tcp",
        name="Modbus TCP",
        short="Modbus TCP",
        family="Modbus",
        role_labels=("主站请求", "从站响应"),
        address_label="从站",
        stream=True,
        parse=lambda raw, **kw: parse_modbus(raw, tcp=True, **kw),
        summary_of=_summary,
    ),
    "modbus_rtu": ProtocolSpec(
        key="modbus_rtu",
        name="Modbus RTU",
        short="Modbus RTU",
        family="Modbus",
        role_labels=("主站请求", "从站响应"),
        address_label="从站",
        stream=True,
        parse=lambda raw, **kw: parse_modbus(raw, tcp=False, **kw),
        summary_of=_summary,
    ),
    "dlt645": ProtocolSpec(
        key="dlt645",
        name="DL/T 645-2007",
        short="DL/T 645",
        family="DL/T 645",
        role_labels=("主站请求", "电表响应"),
        address_label="表地址",
        stream=True,
        parse=parse_dlt645,
        summary_of=_summary,
    ),
    "iec104": ProtocolSpec(
        key="iec104",
        name="IEC 60870-5-104",
        short="IEC 104",
        family="IEC 60870-5",
        role_labels=("请求", "响应"),
        address_label="公共地址",
        stream=True,
        parse=parse_iec104,
        summary_of=_summary,
    ),
    "iec101": ProtocolSpec(
        key="iec101",
        name="IEC 60870-5-101",
        short="IEC 101",
        family="IEC 60870-5",
        role_labels=("请求", "响应"),
        address_label="链路地址",
        stream=True,
        parse=parse_iec101,
        summary_of=_summary,
    ),
    "dnp3": ProtocolSpec(
        key="dnp3",
        name="DNP3",
        short="DNP3",
        family="DNP3",
        role_labels=("主站请求", "从站响应"),
        address_label="源地址",
        stream=True,
        parse=parse_dnp3,
        summary_of=_summary,
    ),
    "mms": ProtocolSpec(
        key="mms",
        name="IEC 61850 MMS",
        short="MMS",
        family="IEC 61850",
        role_labels=("请求", "响应"),
        address_label="—",
        stream=True,
        parse=parse_mms,
        summary_of=_summary,
    ),
    "goose": ProtocolSpec(
        key="goose",
        name="IEC 61850 GOOSE",
        short="GOOSE",
        family="IEC 61850",
        role_labels=("发布", "订阅"),
        address_label="APPID",
        stream=False,
        parse=parse_goose,
        summary_of=_summary,
    ),
}

# 供界面下拉框使用：自动识别 + 全部协议
CHOICES: list[tuple[str, str]] = [(AUTO, "自动识别")] + [
    (spec.key, spec.name) for spec in PROTOCOLS.values()
]


def spec_of(key: str) -> ProtocolSpec:
    return PROTOCOLS.get(key) or PROTOCOLS["modbus_tcp"]


# ---------------------------------------------------------------------------
# 自动识别
# ---------------------------------------------------------------------------


def _score_modbus_tcp(raw: bytes) -> int:
    if len(raw) < 8:
        return 0
    if int.from_bytes(raw[2:4], "big") != 0:
        return 0
    # 功能码必须合法：否则 RTU 帧的长度字节容易与 MBAP 长度字段巧合命中
    if (raw[7] & 0x7F) not in MODBUS_FUNCTIONS:
        return 0
    declared = int.from_bytes(raw[4:6], "big")
    if declared == len(raw) - 6:
        return 95
    return 68 if 2 <= declared <= 254 else 0


def _score_modbus_rtu(raw: bytes) -> int:
    if len(raw) < 4:
        return 0
    if _crc16_modbus(raw[:-2]) != int.from_bytes(raw[-2:], "little"):
        return 0
    # CRC 命中比 MBAP 长度巧合更可信，保证 RTU 优先
    return 96 if (raw[1] & 0x7F) in MODBUS_FUNCTIONS else 88


def _dlt645_start(raw: bytes) -> int:
    limit = min(len(raw), 8)
    for index in range(limit):
        if raw[index] == 0x68:
            return index
    return -1


def _score_dlt645(raw: bytes) -> int:
    start = _dlt645_start(raw)
    if start < 0 or len(raw) < start + 12:
        return 0
    if raw[start + 7] != 0x68:
        return 0
    length = raw[start + 9]
    end = start + 10 + length + 2
    if end > len(raw) or raw[end - 1] != 0x16:
        return 0
    score = 88 if end == len(raw) else 60
    if sum(raw[start : end - 2]) & 0xFF == raw[end - 2]:
        score += 5
    return score


def _score_iec104(raw: bytes) -> int:
    if len(raw) < 6 or raw[0] != 0x68:
        return 0
    declared = raw[1]
    if not 4 <= declared <= 253:
        return 0
    score = 40
    if declared + 2 == len(raw):
        score = 90
    ctrl = raw[2]
    if ctrl & 0x03 == 0x03 or ctrl & 0x01:
        score += 3
    if len(raw) >= 12 and raw[6] in IEC_TYPES:
        score += 4
    return score


def _score_iec101(raw: bytes) -> int:
    if raw == b"\xE5":
        return 72
    if not raw:
        return 0
    if raw[0] == 0x10:
        if len(raw) in (5, 6) and raw[-1] == 0x16:
            return 86
        return 0
    if raw[0] == 0x68:
        if len(raw) < 4 or raw[1] != raw[2] or raw[3] != 0x68:
            return 0
        size = raw[1] + 6
        if size == len(raw) and raw[-1] == 0x16:
            return 90
        return 70 if size <= len(raw) else 0
    return 0


def _dnp3_total_length(raw: bytes) -> int:
    declared = raw[2]
    user_length = max(declared - 5, 0)
    blocks = (user_length + 15) // 16
    return 10 + user_length + 2 * blocks


def _score_dnp3(raw: bytes) -> int:
    if len(raw) < 10 or raw[:2] != b"\x05\x64":
        return 0
    if not 5 <= raw[2] <= 255:
        return 0
    score = 55
    if _dnp3_total_length(raw) == len(raw):
        score = 92
    if _crc16_dnp3(raw[:8]) == int.from_bytes(raw[8:10], "little"):
        score += 5
    return score


def _score_mms(raw: bytes) -> int:
    if len(raw) < 4 or raw[0] != 0x03 or raw[1] != 0x00:
        return 0
    total = int.from_bytes(raw[2:4], "big")
    if total < 4:
        return 0
    score = 85 if total == len(raw) else 62
    if len(raw) > 4 and raw[4] in (0xA0, 0xA1, 0xE0, 0x02, 0x06, 0x07, 0x08):
        score += 5
    return score


def _score_goose(raw: bytes) -> int:
    if len(raw) >= 14 and raw[12:14] == b"\x88\xB8":
        return 99
    if len(raw) >= 18 and raw[12:14] == b"\x81\x00" and raw[16:18] == b"\x88\xB8":
        return 96
    return 0


_SCORERS: list[tuple[str, Callable[[bytes], int]]] = [
    ("goose", _score_goose),
    ("mms", _score_mms),
    ("dnp3", _score_dnp3),
    ("dlt645", _score_dlt645),
    ("iec101", _score_iec101),
    ("iec104", _score_iec104),
    ("modbus_tcp", _score_modbus_tcp),
    ("modbus_rtu", _score_modbus_rtu),
]


def detect_protocol(raw: bytes) -> tuple[str, int]:
    """返回 (协议 key, 置信度)。无法识别时返回 ("", 0)。"""
    if not raw:
        return "", 0
    best_key, best_score = "", 0
    for key, scorer in _SCORERS:
        try:
            score = scorer(raw)
        except (IndexError, ValueError):
            score = 0
        if score > best_score:
            best_key, best_score = key, score
    return best_key, best_score


def is_known(key: str) -> bool:
    return key in PROTOCOLS


# ---------------------------------------------------------------------------
# 解析入口
# ---------------------------------------------------------------------------


def parse_frame(
    raw: bytes,
    protocol: str = AUTO,
    *,
    role: str = ROLE_REQUEST,
    context: dict[str, Any] | None = None,
    link_address_size: int = 1,
) -> dict[str, Any]:
    """解析一帧报文，返回字段级详情。协议不合法时返回错误详情而不是抛异常。"""
    key = protocol
    if key in (AUTO, ""):
        key, _ = detect_protocol(raw)
    if not key:
        return {
            "protocol": "未知协议",
            "protocol_key": "",
            "frame_kind": "未知帧",
            "role": role.lower(),
            "summary": "无法识别该报文的协议类型",
            "purpose": "",
            "valid": False,
            "complete": False,
            "raw_hex": " ".join(f"{byte:02X}" for byte in raw),
            "raw_length": len(raw),
            "fields": [],
            "objects": [],
            "validation": [],
            "correlation": None,
            "warnings": [],
            "errors": ["无法识别协议，请手动指定协议类型"],
        }
    spec = PROTOCOLS[key]
    kwargs: dict[str, Any] = {"role": role}
    if key in ("modbus_tcp", "modbus_rtu", "dnp3"):
        kwargs["request_context"] = context
    if key == "iec101":
        kwargs["link_address_size"] = link_address_size
    try:
        detail = spec.parse(raw, **kwargs)
    except (ValueError, IndexError, KeyError, TypeError, struct.error) as exc:
        detail = {
            "protocol": spec.name,
            "frame_kind": "解析失败",
            "role": role.lower(),
            "summary": f"解析异常：{exc}",
            "purpose": "",
            "valid": False,
            "complete": False,
            "raw_hex": " ".join(f"{byte:02X}" for byte in raw),
            "raw_length": len(raw),
            "fields": [],
            "objects": [],
            "validation": [],
            "correlation": None,
            "warnings": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    detail["protocol_key"] = key
    return detail


def describe(raw: bytes, protocol: str = AUTO, *, role: str = ROLE_REQUEST) -> str:
    """只取摘要，用于列表展示。"""
    return str(parse_frame(raw, protocol, role=role).get("summary") or "")


# ---------------------------------------------------------------------------
# 流式分帧
# ---------------------------------------------------------------------------


def sniff_stream(buf: bytes) -> str | None:
    """根据缓冲区头部判断协议。返回 None 表示字节不足，"" 表示无法识别。"""
    if not buf:
        return ""
    head = buf[0]
    if head == 0x03 and len(buf) >= 2 and buf[1] == 0x00:
        return "mms"
    if head == 0x05 and len(buf) >= 2 and buf[1] == 0x64:
        return "dnp3"
    if head == 0xE5:
        return "iec101"
    if head == 0x10:
        return "iec101"
    if len(buf) >= 4 and _score_modbus_rtu(buf) >= 88:
        return "modbus_rtu"
    if (
        len(buf) >= 8
        and buf[2] == 0
        and buf[3] == 0
        and (buf[7] & 0x7F) in MODBUS_FUNCTIONS
        and 2 <= int.from_bytes(buf[4:6], "big") <= 254
    ):
        return "modbus_tcp"
    if head != 0x68:
        return ""
    if len(buf) < 4:
        return None
    if buf[1] == buf[2] and buf[3] == 0x68:
        return "iec101"
    if 4 <= buf[1] <= 253 and buf[1] + 2 == len(buf):
        return "iec104"
    if len(buf) < 10:
        return None
    if buf[7] == 0x68:
        return "dlt645"
    return "iec104"


def frame_length(protocol: str, buf: bytes, *, link_address_size: int = 1) -> int | None:
    """计算缓冲区首帧长度。

    返回 None 表示需要更多字节；返回 0 表示头部非法需要丢 1 字节重新同步。
    """
    if not buf:
        return None
    if protocol == "modbus_tcp":
        if len(buf) < 6:
            return None
        # MBAP 协议标识必须为 0，否则说明这条流不是 Modbus（例如误抓了别的 TCP 流量）
        if buf[2] != 0 or buf[3] != 0:
            return 0
        declared = int.from_bytes(buf[4:6], "big")
        total = 6 + declared
        if not (8 <= total <= 300 and declared >= 2):
            return 0
        if len(buf) < 8:
            return None
        # 功能码也必须合法，避免字节流里长度字段恰好凑巧而被切成假帧
        if (buf[7] & 0x7F) not in MODBUS_FUNCTIONS:
            return 0
        return total
    if protocol == "modbus_rtu":
        return None
    if protocol == "iec104":
        if len(buf) < 2:
            return None
        declared = buf[1]
        if not 4 <= declared <= 253:
            return 0
        return declared + 2
    if protocol == "dlt645":
        if buf[0] != 0x68:
            return 0
        if len(buf) < 10:
            return None
        if buf[7] != 0x68:
            return 0
        total = 10 + buf[9] + 2
        return total if total <= 300 else 0
    if protocol == "iec101":
        if buf[0] == 0xE5:
            return 1
        if buf[0] == 0x10:
            return 1 + 1 + link_address_size + 2
        if buf[0] != 0x68:
            return 0
        if len(buf) < 4:
            return None
        if buf[1] != buf[2] or buf[3] != 0x68:
            return 0
        total = buf[1] + 6
        return total if total >= 7 else 0
    if protocol == "dnp3":
        if len(buf) < 3:
            return None
        if buf[0] != 0x05 or buf[1] != 0x64:
            return 0
        if not 5 <= buf[2] <= 255:
            return 0
        return _dnp3_total_length(buf)
    if protocol == "mms":
        if len(buf) < 4:
            return None
        if buf[0] != 0x03 or buf[1] != 0x00:
            return 0
        total = int.from_bytes(buf[2:4], "big")
        return total if 4 <= total <= 1_048_576 else 0
    return None


class FrameSplitter:
    """把 TCP 字节流切成完整报文。

    对没有长度字段的协议（Modbus RTU）依赖调用方在链路空闲时调用 ``flush``。
    """

    def __init__(self, protocol: str = AUTO, *, link_address_size: int = 1):
        self.protocol = protocol
        self.link_address_size = link_address_size
        self._buffer = bytearray()

    @property
    def pending(self) -> bytes:
        return bytes(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[bytes]:
        if data:
            self._buffer.extend(data)
        frames: list[bytes] = []
        while self._buffer:
            protocol = self.protocol
            if protocol == AUTO:
                protocol = sniff_stream(bytes(self._buffer))
                if protocol is None:
                    break
                if protocol == "":
                    # 未知头部：缓冲区足够长时丢 1 字节重新同步，过短则等待空闲冲刷
                    if len(self._buffer) >= 8:
                        del self._buffer[:1]
                        continue
                    break
            size = frame_length(protocol, bytes(self._buffer), link_address_size=self.link_address_size)
            if size is None:
                break
            if size <= 0:
                del self._buffer[:1]
                continue
            if size > len(self._buffer):
                break
            frames.append(bytes(self._buffer[:size]))
            del self._buffer[:size]
        return frames

    def flush(self) -> list[bytes]:
        """链路空闲时取出残留数据（用于 RTU 等无长度字段的协议）。"""
        if not self._buffer:
            return []
        raw = bytes(self._buffer)
        self._buffer.clear()
        return [raw]


def frame_address(raw: bytes, protocol: str) -> Any:
    """取出用于列表展示的地址字段（从站地址/链路地址/公共地址等）。"""
    try:
        if protocol == "modbus_tcp":
            return raw[6] if len(raw) >= 7 else None
        if protocol == "modbus_rtu":
            return raw[0] if raw else None
        if protocol == "dlt645":
            start = _dlt645_start(raw)
            if start < 0 or len(raw) < start + 7:
                return None
            return "".join(f"{byte:02X}" for byte in reversed(raw[start + 1 : start + 7]))
        if protocol == "iec104":
            if len(raw) < 12 or raw[2] & 0x01:
                return None
            return int.from_bytes(raw[10:12], "little")
        if protocol == "iec101":
            codec = FT12Codec(link_address_size=1)
            try:
                return codec.decode(raw).link_address
            except FT12Error:
                return None
        if protocol == "dnp3":
            return int.from_bytes(raw[4:6], "little") if len(raw) >= 6 else None
        if protocol == "goose":
            offset = 18 if len(raw) >= 18 and raw[12:14] == b"\x81\x00" else 14
            if len(raw) >= offset + 2:
                return f"0x{int.from_bytes(raw[offset : offset + 2], 'big'):04X}"
    except (IndexError, ValueError):
        return None
    return None
