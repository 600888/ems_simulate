"""Passive IEC 61850 MMS capture over RFC 1006 (TCP/102)."""

from __future__ import annotations

import threading
from typing import Any

from src.device.core.message.message_capture import MessageCapture


class MmsMessageCapture:
    """Capture TCP payloads and expose complete TPKT frames as message records.

    libIEC61850 does not expose its encoded MMS PDUs.  Keeping capture outside the
    library also covers association, discovery, reports, and file services without
    changing every call site in the protocol implementation.
    """

    def __init__(
        self,
        *,
        port: int = 102,
        remote_ip: str = "",
        client: bool,
        max_size: int = 500,
        logger: Any = None,
    ):
        self.port = int(port)
        self.remote_ip = remote_ip if remote_ip not in ("", "0.0.0.0", "::") else ""
        self.client = client
        self._log = logger
        self._messages = MessageCapture(max_size=max_size)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._buffers: dict[tuple[str, int, str, int], bytearray] = {}
        self._next_seq: dict[tuple[str, int, str, int], int] = {}
        self._buffer_lock = threading.Lock()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start asynchronously so a missing Npcap/libpcap never delays MMS startup."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="mms-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._running = False
        with self._buffer_lock:
            self._buffers.clear()
            self._next_seq.clear()

    def get_messages(self, count: int = 100) -> list[dict[str, Any]]:
        return self._messages.get_messages(count)

    def clear(self) -> None:
        self._messages.clear()
        with self._buffer_lock:
            self._buffers.clear()
            self._next_seq.clear()

    def get_avg_time(self) -> dict[str, Any]:
        return self._messages.get_avg_time()

    def _capture_loop(self) -> None:
        try:
            from scapy.all import IP, TCP, IPv6, conf, get_if_list, sniff

            self._running = True
            if self.remote_ip:
                # In particular, 127.0.0.1 must use NPF_Loopback on Windows;
                # Scapy's default interface is normally WLAN/Ethernet and never
                # sees local MMS traffic.
                interface = conf.route.route(self.remote_ip)[0]
            else:
                # An MMS server can accept peers on any local address, including
                # loopback, so listen on every Npcap/libpcap interface.
                interface = get_if_list()
            self._write_log("info", f"MMS报文捕获已启动: port={self.port}, interface={interface}")
            while not self._stop.is_set():
                sniff(
                    iface=interface,
                    filter=f"tcp port {self.port}",
                    prn=lambda packet: self._process_packet(packet, IP, IPv6, TCP),
                    store=False,
                    timeout=1.0,
                    stop_filter=lambda _packet: self._stop.is_set(),
                )
        except Exception as exc:
            # Packet viewing is auxiliary.  Lack of capture permission/Npcap must
            # not prevent the MMS server or client from operating.
            self._write_log("warning", f"MMS报文捕获不可用: {exc}")
        finally:
            self._running = False

    def _write_log(self, level: str, message: str) -> None:
        if self._log is None:
            return
        writer = getattr(self._log, level, None)
        if callable(writer):
            writer(message)

    def _process_packet(self, packet: Any, ip_type: Any, ipv6_type: Any, tcp_type: Any) -> None:
        if not packet.haslayer(tcp_type):
            return
        tcp = packet[tcp_type]
        payload = bytes(tcp.payload)
        if not payload:
            return
        network = packet.getlayer(ip_type) or packet.getlayer(ipv6_type)
        if network is None:
            return
        src, dst = str(network.src), str(network.dst)
        sport, dport = int(tcp.sport), int(tcp.dport)
        if self.remote_ip and self.remote_ip not in (src, dst):
            return
        direction = self._direction(sport, dport)
        key = (src, sport, dst, dport)
        self._accept_segment(key, int(tcp.seq), payload, direction)

    def _direction(self, sport: int, dport: int) -> str:
        if self.client:
            return "TX" if dport == self.port else "RX"
        return "RX" if dport == self.port else "TX"

    def _accept_segment(
        self,
        key: tuple[str, int, str, int],
        sequence: int,
        payload: bytes,
        direction: str,
    ) -> None:
        """Best-effort in-order TCP reassembly, including retransmission trimming."""
        with self._buffer_lock:
            expected = self._next_seq.get(key)
            if expected is not None:
                if sequence < expected:
                    overlap = expected - sequence
                    if overlap >= len(payload):
                        return
                    payload = payload[overlap:]
                    sequence = expected
                elif sequence > expected:
                    # A missing segment makes the old BER stream unusable.  Start
                    # fresh; the TPKT synchronizer below will find the next frame.
                    self._buffers.pop(key, None)
            self._next_seq[key] = sequence + len(payload)
            buffer = self._buffers.setdefault(key, bytearray())
            buffer.extend(payload)
            self._drain_tpkt(buffer, direction)

    def _drain_tpkt(self, buffer: bytearray, direction: str) -> None:
        while buffer:
            start = buffer.find(b"\x03\x00")
            if start < 0:
                buffer.clear()
                return
            if start:
                del buffer[:start]
            if len(buffer) < 4:
                return
            frame_length = int.from_bytes(buffer[2:4], "big")
            if frame_length < 7 or frame_length > 65535:
                del buffer[:2]
                continue
            if len(buffer) < frame_length:
                return
            frame = bytes(buffer[:frame_length])
            del buffer[:frame_length]
            if direction == "TX":
                self._messages.add_tx(frame)
            else:
                self._messages.add_rx(frame)
