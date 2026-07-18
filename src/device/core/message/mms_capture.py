"""Passive IEC 61850 MMS capture over RFC 1006 (TCP/102)."""

from __future__ import annotations

import platform
import threading
import time
from typing import Any

from src.device.core.message.message_capture import MessageCapture


class MmsMessageCapture:
    """Capture TCP payloads and expose complete TPKT frames as message records.

    libIEC61850 does not expose its encoded MMS PDUs. Keeping capture outside the
    library also covers association, discovery, reports, and file services.
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
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._startup_timeout = 3.0
        self._sniffers: list[Any] = []
        self._sniffers_lock = threading.Lock()
        self._buffers: dict[tuple[str, int, str, int], bytearray] = {}
        self._next_seq: dict[tuple[str, int, str, int], int] = {}
        self._buffer_lock = threading.Lock()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, timeout: float = 3.0) -> bool:
        """Start capture and wait until libpcap has opened the selected interface(s)."""
        if self._thread and self._thread.is_alive():
            return self._ready.wait(timeout=max(timeout, 0.0)) and self._running
        self._stop.clear()
        self._ready.clear()
        self._startup_timeout = max(timeout, 0.1)
        self._thread = threading.Thread(target=self._capture_loop, name="mms-capture", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=self._startup_timeout + 0.5):
            self._write_log("warning", f"MMS报文捕获启动超时: port={self.port}")
            return False
        return self._running

    def stop(self) -> None:
        self._stop.set()
        self._stop_sniffers()
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
            from scapy.all import IP, TCP, AsyncSniffer, IPv6, conf, get_if_list

            if self.remote_ip:
                # 127.0.0.1 must resolve to NPF_Loopback on Windows.
                interface: Any = conf.route.route(self.remote_ip)[0]
            else:
                # Servers can accept peers through any local address.
                interface = get_if_list()

            # Scapy 2.7/Npcap accepts a list here on Windows but can silently
            # miss loopback packets. Open one pcap handle per interface instead.
            if platform.system().lower() == "windows" and isinstance(interface, list):
                capture_interfaces = interface
            else:
                capture_interfaces = [interface]

            started_events: list[threading.Event] = []
            sniffers: list[Any] = []
            for capture_interface in capture_interfaces:
                started = threading.Event()
                sniffer = AsyncSniffer(
                    iface=capture_interface,
                    filter=f"tcp port {self.port}",
                    prn=lambda packet: self._process_packet(packet, IP, IPv6, TCP),
                    store=False,
                    started_callback=started.set,
                )
                started_events.append(started)
                sniffers.append(sniffer)

            with self._sniffers_lock:
                self._sniffers = sniffers
            for sniffer in sniffers:
                sniffer.start()

            deadline = time.monotonic() + self._startup_timeout
            while not self._stop.is_set() and time.monotonic() < deadline:
                if all(event.is_set() for event in started_events):
                    break
                time.sleep(0.01)
            if self._stop.is_set():
                return
            if not started_events or not any(event.is_set() for event in started_events):
                raise RuntimeError("Npcap/libpcap 未能打开任何 MMS 抓包网卡")

            self._running = True
            self._ready.set()
            ready_count = sum(event.is_set() for event in started_events)
            self._write_log(
                "info",
                f"MMS报文捕获已启动: port={self.port}, interfaces={ready_count}/{len(started_events)}",
            )
            self._stop.wait()
        except Exception as exc:
            # Packet viewing is auxiliary. Capture failure must not stop MMS.
            self._write_log("warning", f"MMS报文捕获不可用: {exc}")
        finally:
            self._stop_sniffers()
            self._running = False
            self._ready.set()

    def _stop_sniffers(self) -> None:
        """Stop active Scapy workers without letting one bad adapter block cleanup."""
        with self._sniffers_lock:
            sniffers = self._sniffers
            self._sniffers = []
        for sniffer in sniffers:
            try:
                if getattr(sniffer, "running", False):
                    sniffer.stop(join=False)
            except Exception as exc:
                self._write_log("warning", f"停止 MMS 抓包网卡失败: {exc}")

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
                    # A missing segment invalidates the old BER stream. The TPKT
                    # synchronizer will locate the next complete frame.
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
