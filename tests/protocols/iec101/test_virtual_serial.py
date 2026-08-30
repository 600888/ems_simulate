"""In-memory serial-bus integration test for the IEC101 endpoints."""

from __future__ import annotations

import threading
import time

import pytest

from src.proto.iec101.client import IEC101Master
from src.proto.iec101.server import IEC101Slave


class _MemorySerial:
    def __init__(self):
        self.peer = None
        self.is_open = True
        self._buffer = bytearray()
        self._condition = threading.Condition()

    @property
    def in_waiting(self) -> int:
        with self._condition:
            return len(self._buffer)

    def write(self, data: bytes) -> int:
        with self.peer._condition:
            self.peer._buffer.extend(data)
            self.peer._condition.notify_all()
        return len(data)

    def read(self, size: int) -> bytes:
        with self._condition:
            if not self._buffer:
                self._condition.wait(0.01)
            data = bytes(self._buffer[:size])
            del self._buffer[:size]
            return data

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        with self._condition:
            self._buffer.clear()


def _serial_pair() -> tuple[_MemorySerial, _MemorySerial]:
    first, second = _MemorySerial(), _MemorySerial()
    first.peer = second
    second.peer = first
    return first, second


@pytest.mark.parametrize("balanced", [False, True])
def test_master_and_slave_exchange_interrogation_and_command_over_virtual_serial(balanced: bool):
    master_port, slave_port = _serial_pair()
    current_value = {"value": 12.5}
    commands = []
    slave = IEC101Slave(
        port="slave",
        link_addresses=[5],
        common_addresses=[1],
        serial_instance=slave_port,
        balanced=balanced,
    )
    slave.add_point(1, 100, 13, lambda: (current_value["value"], 0))
    slave.set_command_callback(lambda asdu, obj: commands.append((asdu.type_id, obj.io_address, obj.value)) or True)
    master = IEC101Master(
        port="master",
        link_addresses=[5],
        common_addresses=[1],
        serial_instance=master_port,
        poll_interval_ms=10,
        response_timeout_ms=300,
        general_interrogation_on_connect=True,
        balanced=balanced,
    )

    slave.start()
    try:
        assert master.start()
        deadline = time.monotonic() + 1
        while master.cached_value(1, 100) is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert master.cached_value(1, 100) == 12.5
        current_value["value"] = 18.75
        assert master.read(1, 100) == 18.75

        assert master.command(common_address=1, io_address=42, type_id=45, value=1)
        deadline = time.monotonic() + 1
        while not commands and time.monotonic() < deadline:
            time.sleep(0.01)
        assert commands == [(45, 42, 1)]
        assert master.get_captured_messages()
        assert slave.get_captured_messages()
    finally:
        master.stop()
        slave.stop()
