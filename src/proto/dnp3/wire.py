"""DNP3 wire helpers shared by Master and Outstation adapters."""

from __future__ import annotations

from collections.abc import Callable

from pydnp3_pure.link.constants import (
    BROADCAST_ALL,
    BROADCAST_CONFIRM,
    BROADCAST_NO_CONFIRM,
    HEADER_SIZE,
    MAX_USER_DATA,
    MIN_LENGTH_FIELD,
)
from pydnp3_pure.link.frame import extract_user_data, parse_header, wire_frame_size

_BROADCAST_ADDRESSES = {BROADCAST_NO_CONFIRM, BROADCAST_CONFIRM, BROADCAST_ALL}


class FragmentCorrelator:
    """Attach one stable id to every link frame in a transport fragment."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._counter = 0
        self._current_id: str | None = None

    def reset(self) -> None:
        """复位当前传输层分段关联 id。"""
        self._current_id = None

    def metadata(self, raw: bytes) -> dict[str, object]:
        """解析传输层头，为每一传输分段分配稳定的关联 id。"""
        if len(raw) < HEADER_SIZE:
            return {}
        header = parse_header(raw[:HEADER_SIZE])
        if header is None or not header.user_data_length:
            return {}
        user_data = extract_user_data(raw[HEADER_SIZE:], header.user_data_length)
        if not user_data:
            return {}
        transport = user_data[0]
        first = bool(transport & 0x80)
        final = bool(transport & 0x40)
        if first or self._current_id is None:
            self._counter += 1
            self._current_id = f"{self._prefix}-{self._counter}"
        correlation_id = self._current_id
        metadata: dict[str, object] = {
            "fragment_correlation_id": correlation_id,
            "transport_sequence": transport & 0x3F,
            "transport_first": first,
            "transport_final": final,
        }
        if final:
            self._current_id = None
        return metadata


class WireFrameExtractor:
    """Recover validated complete DNP3 link frames from arbitrary TCP chunks."""

    def __init__(self, on_frame: Callable[[bytes], None]) -> None:
        self._on_frame = on_frame
        self._buffer = bytearray()

    def reset(self) -> None:
        """清空内部接收缓冲。"""
        self._buffer.clear()

    def data_received(self, data: bytes) -> None:
        """从任意 TCP 分块中提取完整链路帧并回调。"""
        self._buffer.extend(data)
        while True:
            sync = self._buffer.find(b"\x05\x64")
            if sync < 0:
                self._buffer[:] = self._buffer[-1:] if self._buffer[-1:] == b"\x05" else b""
                return
            if sync:
                del self._buffer[:sync]
            if len(self._buffer) < HEADER_SIZE:
                return
            header = parse_header(self._buffer[:HEADER_SIZE])
            if header is None or header.length < MIN_LENGTH_FIELD or header.user_data_length > MAX_USER_DATA:
                del self._buffer[:1]
                continue
            frame_size = wire_frame_size(header.user_data_length)
            if len(self._buffer) < frame_size:
                return
            raw = bytes(self._buffer[:frame_size])
            del self._buffer[:frame_size]
            if extract_user_data(raw[HEADER_SIZE:], header.user_data_length) is not None:
                self._on_frame(raw)


def accepts_link_address(destination: int, source: int, *, local: int, remote: int) -> bool:
    """Return whether a received link frame belongs to the configured point-to-point session."""
    destination_matches = destination == local or destination in _BROADCAST_ADDRESSES
    return destination_matches and source == remote
