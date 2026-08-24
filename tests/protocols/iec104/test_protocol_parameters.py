import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import c104

import src.proto.iec104.iec104client as iec104client_module
from src.proto.iec104.iec104client import IEC104Client
import src.proto.iec104.iec104server as iec104server_module
from src.proto.iec104.iec104server import IEC104Server


def _parameter_values(parameters):
    return {
        "k": parameters.send_window_size,
        "w": parameters.receive_window_size,
        "t0": parameters.connection_timeout,
        "t1": parameters.message_timeout,
        "t2": parameters.confirm_interval,
        "t3": parameters.keep_alive_interval,
    }


def test_client_applies_link_parameters_and_originator_address():
    client = IEC104Client(
        send_window_size=16,
        receive_window_size=10,
        connection_timeout=4,
        message_timeout=5,
        confirm_interval=2,
        keep_alive_interval=21,
        originator_address=7,
    )

    assert client.client.originator_address == 7
    assert client.connection.originator_address == 7
    assert _parameter_values(client.connection.protocol_parameters) == {
        "k": 16,
        "w": 10,
        "t0": 4,
        "t1": 5,
        "t2": 2,
        "t3": 21,
    }


def test_client_can_disable_general_interrogation_on_connect(monkeypatch):
    captured = {}

    class FakeConnection:
        def __init__(self):
            self.originator_address = 0
            self.protocol_parameters = SimpleNamespace()

        def on_receive_raw(self, callable):
            pass

        def on_send_raw(self, callable):
            pass

        def on_state_change(self, callable):
            pass

    class FakeClient:
        def __init__(self, transport_security=None):
            self.originator_address = 0

        def add_connection(self, **kwargs):
            captured.update(kwargs)
            return FakeConnection()

    monkeypatch.setattr(iec104client_module.c104, "Client", FakeClient)

    IEC104Client(general_interrogation_on_connect=False)

    assert captured["init"] is c104.Init.NONE


def test_server_applies_all_link_parameters():
    server = IEC104Server(
        ip="127.0.0.1",
        port=0,
        send_window_size=18,
        receive_window_size=11,
        connection_timeout=6,
        message_timeout=7,
        confirm_interval=3,
        keep_alive_interval=22,
    )

    assert _parameter_values(server.server.protocol_parameters) == {
        "k": 18,
        "w": 11,
        "t0": 6,
        "t1": 7,
        "t2": 3,
        "t3": 22,
    }


def test_server_disables_fork_monitoring_for_official_c104(monkeypatch):
    captured_kwargs = {}

    class OfficialServerStub:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.protocol_parameters = SimpleNamespace()
            self.max_connections = 0

        def on_receive_raw(self, callable):
            pass

        def on_send_raw(self, callable):
            pass

    monkeypatch.setattr(iec104server_module, "_has_connection_monitoring_extension", lambda: False)
    monkeypatch.setattr(iec104server_module.c104, "Server", OfficialServerStub)

    server = IEC104Server(ip="127.0.0.1", port=2404)

    assert "connection_history_size" not in captured_kwargs
    assert server.connection_monitoring_supported is False


def test_server_module_imports_without_fork_connection_types(monkeypatch):
    class OfficialC104Proxy(ModuleType):
        def __getattr__(self, name):
            if name in {"ServerConnection", "ServerConnectionState"}:
                raise AttributeError(name)
            return getattr(c104, name)

    monkeypatch.setitem(sys.modules, "c104", OfficialC104Proxy("c104"))
    spec = importlib.util.spec_from_file_location(
        "tests.iec104server_official_compat",
        iec104server_module.__file__,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    server = module.IEC104Server(ip="127.0.0.1", port=0)

    assert module.ServerConnection is Any
    assert module.ServerConnectionState is Any
    assert server.connection_monitoring_supported is False
