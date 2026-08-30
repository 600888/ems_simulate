"""Small pyserial adapter used by IEC 101 master and slave endpoints."""

from __future__ import annotations

import threading
import time
from typing import Any

import serial

from src.device.core.message.message_capture import MessageCapture
from src.proto.iec101.ft12 import FT12Codec, FT12Frame, FT12StreamDecoder


class SerialFT12Endpoint:
    def __init__(
        self,
        *,
        port: str,
        baudrate: int = 9600,
        databits: int = 8,
        stopbits: int = 1,
        parity: str = "E",
        link_address_size: int = 1,
        response_timeout_ms: int = 1000,
        serial_instance: Any | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.databits = databits
        self.stopbits = stopbits
        self.parity = parity
        self.response_timeout = response_timeout_ms / 1000.0
        self.codec = FT12Codec(link_address_size=link_address_size)
        self.decoder = FT12StreamDecoder(self.codec)
        self.message_capture = MessageCapture()
        self._serial = serial_instance
        self._owns_serial = serial_instance is None
        self._write_lock = threading.RLock()
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open and self._serial is not None and bool(getattr(self._serial, "is_open", True))

    def open(self) -> None:
        if self.is_open:
            return
        if self._serial is None:
            self._serial = serial.serial_for_url(
                self.port,
                baudrate=self.baudrate,
                bytesize=self.databits,
                stopbits=self.stopbits,
                parity=self.parity,
                timeout=0.05,
                write_timeout=self.response_timeout,
            )
        elif hasattr(self._serial, "open") and not getattr(self._serial, "is_open", True):
            self._serial.open()
        self._open = True
        if hasattr(self._serial, "reset_input_buffer"):
            self._serial.reset_input_buffer()

    def close(self) -> None:
        self._open = False
        if self._serial is not None and self._owns_serial and hasattr(self._serial, "close"):
            self._serial.close()

    def write_frame(self, data: bytes) -> None:
        if not self.is_open:
            raise ConnectionError("IEC101 serial port is not open")
        with self._write_lock:
            self._serial.write(data)
            if hasattr(self._serial, "flush"):
                self._serial.flush()
            self.message_capture.add_tx(data)

    def read_frames(self, timeout: float | None = None) -> list[tuple[bytes, FT12Frame]]:
        deadline = time.monotonic() + (self.response_timeout if timeout is None else timeout)
        while self.is_open and time.monotonic() < deadline:
            waiting = int(getattr(self._serial, "in_waiting", 0) or 0)
            data = self._serial.read(max(1, waiting))
            if data:
                frames = self.decoder.feed(data)
                for raw, _frame in frames:
                    self.message_capture.add_rx(raw)
                if frames:
                    return frames
            else:
                time.sleep(0.005)
        return []

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.message_capture.get_messages(limit)

    def clear_captured_messages(self) -> None:
        self.message_capture.clear()
