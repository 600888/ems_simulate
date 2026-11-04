"""报文记录仓库：保存会话内报文、推导角色、关联请求与响应。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import threading
import time
from typing import Any

from . import registry


def format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]


@dataclass
class FrameRecord:
    """一帧报文的原始记录。

    ``src_ip`` 等网络字段仅在网卡抓包模式下有值，离线导入时留空。
    """

    sequence: int
    timestamp: float
    direction: str
    raw: bytes
    protocol: str
    role: str
    source: str = ""
    src_ip: str = ""
    src_port: int = 0
    dst_ip: str = ""
    dst_port: int = 0
    transport: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def hex_data(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.raw)

    @property
    def formatted_time(self) -> str:
        return format_time(self.timestamp)

    @property
    def endpoint_text(self) -> str:
        """源 → 目的 的展示文本；无 IP 信息时留空。"""
        if not self.src_ip and not self.dst_ip:
            return ""
        return f"{self.endpoint(self.src_ip, self.src_port)} → {self.endpoint(self.dst_ip, self.dst_port)}"

    @staticmethod
    def endpoint(ip: str, port: int) -> str:
        if not ip:
            return "—"
        return f"{ip}:{port}" if port else ip

    def matches_ip(self, keyword: str) -> bool:
        """按 IP 片段匹配，忽略端口。"""
        needle = (keyword or "").strip().lower()
        if not needle:
            return True
        if not self.src_ip and not self.dst_ip:
            return False
        return needle in self.src_ip.lower() or needle in self.dst_ip.lower()


class MessageStore:
    """会话内报文集合，负责解析缓存与请求/响应关联。"""

    def __init__(self, max_size: int = 5000):
        self.max_size = max_size
        self._records: list[FrameRecord] = []
        self._sequence = 0
        self._lock = threading.RLock()
        self._summary_cache: dict[int, str] = {}
        self._detail_cache: dict[int, dict[str, Any]] = {}
        self._tx_count = 0
        self._rx_count = 0
        self._pending_tx = 0.0
        self._pending_rx = 0.0
        self._pair_count = 0
        self._total_latency = 0.0

    # -- 基础操作 ---------------------------------------------------------
    def __len__(self) -> int:
        return len(self._records)

    @property
    def records(self) -> list[FrameRecord]:
        return self._records

    def get(self, sequence: int) -> FrameRecord | None:
        return next((record for record in self._records if record.sequence == sequence), None)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._summary_cache.clear()
            self._detail_cache.clear()
            self._sequence = 0
            self._tx_count = self._rx_count = 0
            self._pair_count = 0
            self._total_latency = 0.0
            self._pending_tx = self._pending_rx = 0.0

    def invalidate(self) -> None:
        """清空派生缓存，批量导入后重新计算摘要与关联。"""
        with self._lock:
            self._summary_cache.clear()
            self._detail_cache.clear()

    def append(
        self,
        direction: str,
        raw: bytes,
        protocol: str = registry.AUTO,
        *,
        role: str = "",
        source: str = "",
        src_ip: str = "",
        src_port: int = 0,
        dst_ip: str = "",
        dst_port: int = 0,
        transport: str = "",
    ) -> FrameRecord:
        if not raw:
            raise ValueError("empty frame")
        with self._lock:
            resolved = protocol
            if resolved in (registry.AUTO, ""):
                detected, _score = registry.detect_protocol(raw)
                resolved = detected
            if not role:
                role = registry.ROLE_REQUEST if direction == "TX" else registry.ROLE_RESPONSE
            self._sequence += 1
            record = FrameRecord(
                sequence=self._sequence,
                timestamp=time.time(),
                direction=direction,
                raw=bytes(raw),
                protocol=resolved,
                role=role,
                source=source,
                src_ip=src_ip,
                src_port=int(src_port or 0),
                dst_ip=dst_ip,
                dst_port=int(dst_port or 0),
                transport=transport,
            )
            self._records.append(record)
            self._account_latency(direction)
            if len(self._records) > self.max_size:
                dropped = self._records[: len(self._records) - self.max_size]
                self._records = self._records[-self.max_size :]
                for item in dropped:
                    self._summary_cache.pop(item.sequence, None)
                    self._detail_cache.pop(item.sequence, None)
            return record

    def _account_latency(self, direction: str) -> None:
        now = time.time()
        if direction == "TX":
            self._tx_count += 1
            if self._pending_rx > 0:
                self._total_latency += now - self._pending_rx
                self._pair_count += 1
                self._pending_rx = 0.0
            else:
                self._pending_tx = now
        else:
            self._rx_count += 1
            if self._pending_tx > 0:
                self._total_latency += now - self._pending_tx
                self._pair_count += 1
                self._pending_tx = 0.0
            else:
                self._pending_rx = now

    def stats(self) -> dict[str, Any]:
        avg = round(self._total_latency / self._pair_count * 1000, 2) if self._pair_count else 0.0
        return {
            "tx_count": self._tx_count,
            "rx_count": self._rx_count,
            "pair_count": self._pair_count,
            "avg_latency_ms": avg,
        }

    # -- 解析 -------------------------------------------------------------
    def summary(self, sequence: int) -> str:
        cached = self._summary_cache.get(sequence)
        if cached is not None:
            return cached
        record = self.get(sequence)
        if record is None:
            return ""
        detail = self.detail(sequence)
        text = str(detail.get("summary") or "")
        self._summary_cache[sequence] = text
        return text

    def detail(self, sequence: int) -> dict[str, Any]:
        cached = self._detail_cache.get(sequence)
        if cached is not None:
            return cached
        record = self.get(sequence)
        if record is None:
            return {}
        context = self._request_context(record)
        detail = registry.parse_frame(
            record.raw,
            record.protocol,
            role=record.role,
            context=context,
        )
        detail.update(
            sequence_id=record.sequence,
            direction=record.direction,
            msg_type=record.role,
            timestamp=record.timestamp,
            formatted_time=record.formatted_time,
            source=record.source,
            address=registry.frame_address(record.raw, record.protocol),
            protocol_name=registry.PROTOCOLS[record.protocol].name if record.protocol else "未知协议",
            src_ip=record.src_ip,
            src_port=record.src_port,
            dst_ip=record.dst_ip,
            dst_port=record.dst_port,
            transport=record.transport,
            endpoint=record.endpoint_text,
        )
        self._detail_cache[sequence] = detail
        return detail

    def _request_context(self, record: FrameRecord) -> dict[str, Any] | None:
        if record.role != registry.ROLE_RESPONSE:
            return None
        index = self._records.index(record)
        if record.protocol in ("modbus_tcp", "modbus_rtu"):
            return self._modbus_context(index)
        if record.protocol == "dnp3":
            return self._dnp3_context(index)
        return None

    def _modbus_context(self, index: int) -> dict[str, Any] | None:
        record = self._records[index]
        is_tcp = record.protocol == "modbus_tcp"
        try:
            response = record.raw
            unit = response[6] if is_tcp else response[0]
            function = (response[7] if is_tcp else response[1]) & 0x7F
            transaction = int.from_bytes(response[:2], "big") if is_tcp else None
        except IndexError:
            return None
        for candidate in reversed(self._records[:index]):
            if candidate.role != registry.ROLE_REQUEST:
                continue
            if candidate.protocol != record.protocol:
                continue
            info = _modbus_request_info(candidate.raw, is_tcp)
            if not info or info["unit"] != unit or info["function"] != function:
                continue
            if is_tcp and int.from_bytes(candidate.raw[:2], "big") != transaction:
                continue
            return {
                "request_sequence_id": candidate.sequence,
                "start_address": info["start"],
                "end_address": info["end"],
                "quantity": info["end"] - info["start"] + 1,
                "match_method": "transaction_id" if is_tcp else "slave_function_time_order",
            }
        return None

    def _dnp3_context(self, index: int) -> dict[str, Any] | None:
        record = self._records[index]
        try:
            current = registry.parse_frame(record.raw, "dnp3", role=record.role)
        except (ValueError, IndexError):
            return None
        if current.get("application_function_code") not in (129, 130):
            return None
        sequence = current.get("application_sequence")
        if sequence is None:
            return None
        for candidate in reversed(self._records[:index]):
            if candidate.role != registry.ROLE_REQUEST or candidate.protocol != "dnp3":
                continue
            try:
                parsed = registry.parse_frame(candidate.raw, "dnp3", role=registry.ROLE_REQUEST)
            except (ValueError, IndexError):
                continue
            if parsed.get("application_sequence") != sequence:
                continue
            return {
                "application_sequence": sequence,
                "request_sequence_id": candidate.sequence,
                "request_function_code": parsed.get("application_function_code"),
                "request_function": parsed.get("application_function"),
                "match_method": "application_sequence",
            }
        return None


def _modbus_request_info(raw: bytes, is_tcp: bool) -> dict[str, Any] | None:
    if is_tcp:
        if len(raw) < 8:
            return None
        unit, pdu = raw[6], raw[7:]
    else:
        if len(raw) < 4:
            return None
        unit, pdu = raw[0], raw[1:-2]
    if not pdu:
        return None
    function = pdu[0] & 0x7F
    if function in (1, 2, 3, 4) and len(pdu) == 5:
        start = int.from_bytes(pdu[1:3], "big")
        count = int.from_bytes(pdu[3:5], "big")
        return {"unit": unit, "function": function, "start": start, "end": start + count - 1}
    if function in (5, 6) and len(pdu) >= 5:
        address = int.from_bytes(pdu[1:3], "big")
        return {"unit": unit, "function": function, "start": address, "end": address}
    if function in (15, 16) and len(pdu) > 5:
        start = int.from_bytes(pdu[1:3], "big")
        count = int.from_bytes(pdu[3:5], "big")
        return {"unit": unit, "function": function, "start": start, "end": start + count - 1}
    return None
