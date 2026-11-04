"""TCP 实时抓包引擎（纯 Python，不依赖 Qt）。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
import socket
import threading
import time

from . import registry


@dataclass
class CaptureConfig:
    """抓包参数。"""

    mode: str = "client"  # client：主动连接；server：监听等待
    host: str = "127.0.0.1"
    port: int = 502
    protocol: str = registry.AUTO
    link_address_size: int = 1
    poll_hex: str = ""
    poll_interval: float = 1.0
    idle_gap: float = 0.05

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CaptureConfig:
        allowed = {field for field in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})


FrameCallback = Callable[[bytes, str], None]
StatusCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]


class CaptureEngine:
    """在后台线程中收发报文，按协议分帧后回调上层。"""

    def __init__(
        self,
        config: CaptureConfig,
        *,
        on_frame: FrameCallback | None = None,
        on_status: StatusCallback | None = None,
        on_error: ErrorCallback | None = None,
    ):
        self.config = config
        self._on_frame = on_frame or (lambda *_: None)
        self._on_status = on_status or (lambda *_: None)
        self._on_error = on_error or (lambda *_: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._frames = 0
        self._poll_bytes = _parse_hex(config.poll_hex)
        self._failed = False

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def frame_count(self) -> int:
        return self._frames

    # -- 生命周期 ---------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="packet-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._close()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _close(self) -> None:
        with self._lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            with suppress(OSError):
                sock.close()

    # -- 发送 -------------------------------------------------------------
    def send_hex(self, text: str) -> bool:
        raw = _parse_hex(text)
        if not raw:
            return False
        sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall(raw)
        except OSError:
            return False
        self._emit(raw, "TX")
        return True

    def _emit(self, raw: bytes, direction: str) -> None:
        self._frames += 1
        self._on_frame(raw, direction, self._meta(direction))

    def _meta(self, direction: str):
        """直连模式只有一个对端，尽量补齐 IP 信息以便和网卡模式统一展示。"""
        from .pcap import FrameMeta

        host, port = self.config.host, int(self.config.port)
        if self.config.mode == "client":
            endpoints = (host, port, "本机", 0) if direction == "TX" else ("本机", 0, host, port)
        else:
            endpoints = ("本机", port, "客户端", 0) if direction == "TX" else ("客户端", 0, "本机", port)
        return FrameMeta(
            src_ip=endpoints[0],
            src_port=endpoints[1],
            dst_ip=endpoints[2],
            dst_port=endpoints[3],
            transport="TCP",
            role=self._role(direction),
        )

    def _role(self, direction: str) -> str:
        if self.config.mode == "server":
            return registry.ROLE_REQUEST if direction == "RX" else registry.ROLE_RESPONSE
        return registry.ROLE_REQUEST if direction == "TX" else registry.ROLE_RESPONSE

    # -- 主循环 -----------------------------------------------------------
    def _run(self) -> None:
        self._failed = False
        try:
            if self.config.mode == "server":
                self._run_server()
            else:
                self._run_client()
        except ConnectionRefusedError:
            self._failed = True
            self._on_error(f"连接被拒绝：{self.config.host}:{self.config.port}")
        except TimeoutError:
            self._failed = True
            self._on_error("连接超时，请检查目标地址与端口")
        except OSError as exc:
            if not self._stop.is_set():
                self._failed = True
                self._on_error(str(exc))
        except Exception as exc:  # noqa: BLE001 - 后台线程需要兜底
            self._failed = True
            self._on_error(f"{type(exc).__name__}: {exc}")
        finally:
            self._close()
            self._thread = None
            if self._stop.is_set():
                self._on_status("抓包已停止")
            elif not self._failed:
                self._on_status("连接已断开")

    def _run_client(self) -> None:
        sock = socket.create_connection((self.config.host, self.config.port), timeout=3.0)
        sock.settimeout(0.05)
        with self._lock:
            self._sock = sock
        self._on_status(f"已连接 {self.config.host}:{self.config.port}")
        self._pump(sock)

    def _run_server(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.config.host, self.config.port))
        server.listen(1)
        server.settimeout(0.2)
        self._on_status(f"监听 {self.config.host}:{self.config.port}，等待设备连接…")
        try:
            while not self._stop.is_set():
                try:
                    conn, address = server.accept()
                except TimeoutError:
                    continue
                conn.settimeout(0.05)
                with self._lock:
                    self._sock = conn
                self._on_status(f"已接受 {address[0]}:{address[1]}")
                try:
                    self._pump(conn)
                finally:
                    with self._lock:
                        self._sock = None
                    with suppress(OSError):
                        conn.close()
                if not self._stop.is_set():
                    self._on_status("连接已断开，继续监听…")
        finally:
            server.close()

    def _pump(self, sock: socket.socket) -> None:
        splitter = registry.FrameSplitter(self.config.protocol, link_address_size=self.config.link_address_size)
        idle_gap = max(self.config.idle_gap, 0.005)
        interval = max(self.config.poll_interval, 0.05)
        last_data = time.time()
        next_poll = 0.0
        while not self._stop.is_set():
            now = time.time()
            try:
                data = sock.recv(65536)
                if not data:
                    self._on_status("对端已关闭连接")
                    break
                last_data = now
                for frame in splitter.feed(data):
                    self._emit(frame, "RX")
            except TimeoutError:
                pass
            except OSError:
                break

            now = time.time()
            if splitter.pending:
                idle_ready = now - last_data >= idle_gap
                if idle_ready and self.config.protocol in (registry.AUTO, "modbus_rtu"):
                    for frame in splitter.flush():
                        self._emit(frame, "RX")
                elif len(splitter.pending) > 65536:
                    splitter.reset()

            if self._poll_bytes and now >= next_poll:
                try:
                    sock.sendall(self._poll_bytes)
                except OSError:
                    break
                self._emit(self._poll_bytes, "TX")
                next_poll = now + interval


def _parse_hex(text: str) -> bytes:
    cleaned = "".join(ch for ch in (text or "") if ch in "0123456789abcdefABCDEF")
    if len(cleaned) % 2:
        cleaned = cleaned[:-1]
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return b""
