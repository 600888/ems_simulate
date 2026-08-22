from __future__ import annotations

import asyncio
from types import SimpleNamespace

import c104
import pytest

from src.device.core.data.data_reader import DataReader
from src.device.core.point.point_operator import PointOperator
from src.device.protocol.iec104_handler import IEC104ClientHandler, IEC104ServerHandler
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yt


class _FakeClient:
    is_connected = True
    stations: dict = {}

    def __init__(self, read_value=100):
        self.read_value = read_value
        self.written = None

    def read_point(self, **_kwargs):
        return self.read_value

    def active_read_point(self, **_kwargs):
        return self.read_value

    def write_point(self, **kwargs):
        self.written = kwargs["value"]
        return True


class _FakeServer:
    def __init__(self, read_value=100):
        self.read_value = read_value
        self.written = None

    def get_point_value(self, **_kwargs):
        return self.read_value

    def set_point_value(self, **kwargs):
        self.written = kwargs["value"]

    def set_point_quality(self, **_kwargs):
        pass


def _connected_client_handler(client: _FakeClient) -> IEC104ClientHandler:
    handler = IEC104ClientHandler()
    handler._client = client
    handler._is_running = True
    return handler


def test_client_read_returns_raw_value_and_point_applies_coefficients():
    point = Yc(
        value=0,
        mul_coe=0.1,
        add_coe=5,
        decode="0x41",
        iec_type_id="M_ME_NB_1",
    )
    handler = _connected_client_handler(_FakeClient(read_value=c104.Int16(100)))

    raw_value = handler.read_value(point)
    point.value = raw_value

    assert raw_value == 100
    assert point.value == 100
    assert point.real_value == 15


def test_client_write_sends_raw_value_calculated_by_point():
    point = Yt(
        value=0,
        mul_coe=0.1,
        add_coe=5,
        decode="0x41",
        iec_type_id="C_SE_NB_1",
    )
    assert point.set_real_value(15)
    client = _FakeClient()
    handler = _connected_client_handler(client)

    assert handler.write_value(point, point.value)

    assert point.value == 100
    assert float(client.written) == 100


def test_client_active_read_returns_raw_value():
    point = Yc(
        value=0,
        mul_coe=0.1,
        add_coe=5,
        decode="0x41",
        iec_type_id="M_ME_NB_1",
    )
    handler = _connected_client_handler(_FakeClient(read_value=c104.Int16(100)))

    raw_value = asyncio.run(handler.active_read_value_async(point))
    point.value = raw_value

    assert raw_value == 100
    assert point.real_value == 15


def test_server_read_and_write_use_raw_value():
    point = Yc(
        value=0,
        mul_coe=0.1,
        add_coe=5,
        decode="0x41",
        iec_type_id="M_ME_NB_1",
    )
    server = _FakeServer(read_value=c104.Int16(100))
    handler = IEC104ServerHandler()
    handler._server = server

    raw_value = handler.read_value(point)
    point.value = raw_value
    assert handler.write_value(point, point.value)

    assert point.real_value == 15
    assert float(server.written) == 100


def test_server_command_updates_raw_value_then_point_calculates_real_value():
    point = Yt(
        value=0,
        mul_coe=0.1,
        add_coe=5,
        decode="0x41",
        iec_type_id="C_SE_NB_1",
    )
    handler = IEC104ServerHandler()
    handler._command_point_map[(1, 25089)] = point

    handler._on_command_received(25089, c104.Int16(100), c104.Type.C_SE_NB_1, 1)

    assert point.value == 100
    assert point.real_value == 15


def test_unsolicited_client_sync_stores_raw_value():
    point = Yc(
        value=0,
        mul_coe=0.1,
        add_coe=5,
        decode="0x41",
        iec_type_id="M_ME_NB_1",
    )
    c104_point = SimpleNamespace(value=c104.Int16(100), quality=None)
    station = SimpleNamespace(get_point=lambda **_kwargs: c104_point)
    client = _FakeClient()
    client.stations = {1: station}
    handler = _connected_client_handler(client)
    device = SimpleNamespace(
        protocol_handler=handler,
        point_manager=SimpleNamespace(get_points_by_slave=lambda _slave_id: ([point], [], [], [])),
        log=SimpleNamespace(error=lambda *_args: None, debug=lambda *_args: None),
        ip="127.0.0.1",
        port=2404,
        serial_port=None,
    )

    DataReader(device).sync_iec104_client_values(1)

    assert point.value == 100
    assert point.real_value == 15


class _MetadataHandler:
    def __init__(self):
        self.written = []

    def write_value(self, point, value):
        self.written.append((point, value))
        return True


@pytest.mark.parametrize("protocol_type", [ProtocolType.ModbusTcpServer, ProtocolType.Iec104Server])
def test_yc_coefficient_edit_has_same_result_as_modbus(monkeypatch, protocol_type):
    point = Yc(value=100, mul_coe=0.1, add_coe=0, decode="0x41", iec_type_id="M_ME_NB_1")
    handler = _MetadataHandler()
    device = SimpleNamespace(
        name="device",
        protocol_type=protocol_type,
        protocol_handler=handler,
        point_manager=SimpleNamespace(get_point_by_code=lambda _code: point),
        log=SimpleNamespace(info=lambda *_args: None, warning=lambda *_args: None, error=lambda *_args: None),
    )
    operator = PointOperator(device)
    monkeypatch.setattr(operator, "_get_channel_id", lambda: 1)
    monkeypatch.setattr(
        "src.device.core.point.point_operator.PointService.update_point_metadata",
        lambda *_args, **_kwargs: True,
    )

    assert operator.edit_metadata("POINT", {"mul_coe": 0.2, "add_coe": 5})

    assert point.value == 100
    assert point.real_value == 25
    assert handler.written == []


@pytest.mark.parametrize("protocol_type", [ProtocolType.ModbusTcpServer, ProtocolType.Iec104Server])
def test_yt_coefficient_edit_has_same_result_as_modbus(monkeypatch, protocol_type):
    point = Yt(value=100, mul_coe=0.1, add_coe=5, decode="0x41", iec_type_id="C_SE_NB_1")
    handler = _MetadataHandler()
    device = SimpleNamespace(
        name="device",
        protocol_type=protocol_type,
        protocol_handler=handler,
        point_manager=SimpleNamespace(get_point_by_code=lambda _code: point),
        log=SimpleNamespace(info=lambda *_args: None, warning=lambda *_args: None, error=lambda *_args: None),
    )
    operator = PointOperator(device)
    monkeypatch.setattr(operator, "_get_channel_id", lambda: 1)
    monkeypatch.setattr(
        "src.device.core.point.point_operator.PointService.update_point_metadata",
        lambda *_args, **_kwargs: True,
    )

    assert operator.edit_metadata("POINT", {"mul_coe": 0.2, "add_coe": 10})

    assert point.real_value == 15
    assert point.value == 25
    assert handler.written[-1][1] == 25
