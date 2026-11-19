"""Exercise select and execute using an external, raw IEC104 TCP peer."""

import socket
import struct

import pytest

from src.device.protocol.iec104_handler import IEC104ServerHandler
from src.enums.point_data import Yk, Yt
from src.proto.iec104.iec104server import IEC104Server


class _Peer:
    def __init__(self, connection):
        self.connection = connection
        self.send_sequence = 0
        self.receive_sequence = 0
        connection.settimeout(3)
        connection.sendall(bytes.fromhex("68 04 07 00 00 00"))
        assert self.receive() == bytes.fromhex("68 04 0b 00 00 00")

    def _read(self, size):
        result = bytearray()
        while len(result) < size:
            data = self.connection.recv(size - len(result))
            assert data, "Server closed the connection before confirming the command"
            result.extend(data)
        return bytes(result)

    def receive(self):
        header = self._read(2)
        assert header[0] == 0x68
        frame = header + self._read(header[1])
        if not frame[2] & 1:
            self.receive_sequence = int.from_bytes(frame[2:4], "little") + 2
        return frame

    def command(self, type_id, payload, *, select=False):
        payload = payload[:-1] + bytes([payload[-1] | (0x80 if select else 0)])
        asdu = bytes([type_id, 1, 6, 0, 1, 0, 100, 0, 0]) + payload
        control = struct.pack("<HH", self.send_sequence, self.receive_sequence)
        self.send_sequence += 2
        self.connection.sendall(bytes([0x68, len(asdu) + 4]) + control + asdu)
        for _ in range(8):
            frame = self.receive()
            if len(frame) > 6 and frame[6] == type_id and frame[8] & 0x3F == 7:
                return frame[8], frame[-1]
        pytest.fail("No activation confirmation received")


@pytest.mark.parametrize(
    "point_class,type_name,type_id,payload",
    [
        (Yk, "C_SC_NA_1", 45, b"\x01"),
        (Yk, "C_DC_NA_1", 46, b"\x02"),
        (Yt, "C_SE_NC_1", 50, struct.pack("<fB", 12.5, 0)),
    ],
)
def test_external_client_select_and_execute_after_live_mode_edit(point_class, type_name, type_id, payload):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = IEC104Server(ip="127.0.0.1", port=port)
    handler = IEC104ServerHandler()
    handler._server = server
    point = point_class(code="CMD", address="0x0064", iec_type_id=type_name)
    handler.add_points([point])
    received = []
    server.set_on_command_callback(lambda *args: received.append(args))
    server.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
            peer = _Peer(connection)
            # Legacy direct mode still accepts execution and rejects selection.
            assert peer.command(type_id, payload, select=True)[0] == 0x47
            assert received == []
            assert peer.command(type_id, payload)[0] == 0x07
            assert len(received) == 1

            handler.update_command_mode(point, "SELECT_AND_EXECUTE")
            # The new workflow rejects execution before a successful selection.
            assert peer.command(type_id, payload)[0] == 0x47
            assert len(received) == 1
            cot, qualifier = peer.command(type_id, payload, select=True)
            assert cot == 0x07
            assert qualifier & 0x80
            assert len(received) == 1
            assert peer.command(type_id, payload)[0] == 0x07
            assert len(received) == 2
    finally:
        server.stop()
