import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.web.api.channel import iec61850 as iec61850_api


class _FakeFiles:
    def __init__(self):
        self.list_calls = 0

    def list_directory(self, _directory=""):
        self.list_calls += 1
        return []


class _FakeReports:
    def __init__(self):
        self.discovery_calls = 0

    def discover_rcbs(self):
        self.discovery_calls += 1
        return []


class _FakeClient:
    def __init__(self, *, connected: bool):
        self.is_connected = connected
        self._conn = SimpleNamespace(is_connected=connected)
        self.files = _FakeFiles()
        self.reports = _FakeReports()

    def browse_logical_devices(self):
        return []


def _build_request(handler: IEC61850ClientHandler):
    device = SimpleNamespace(protocol_handler=handler, point_manager=None, slave_id_list=[])
    controller = SimpleNamespace(get_device_by_channel_id=lambda _channel_id: device)
    state = SimpleNamespace(device_controller=controller, goose_manager=None)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _call_structure(handler: IEC61850ClientHandler):
    request = _build_request(handler)
    body = iec61850_api.Iec61850StructureRequest(channel_id=37)
    fake_log = Mock()
    with (
        patch.object(iec61850_api.ChannelService, "get_channel_by_id", return_value={"protocol_type": 4}),
        patch.object(iec61850_api, "log", fake_log),
    ):
        response = asyncio.run(iec61850_api.get_iec61850_structure(body, request))
    return response, fake_log


def test_structure_query_does_not_probe_remote_services_when_client_is_stopped():
    handler = IEC61850ClientHandler()
    client = _FakeClient(connected=False)
    handler._client = client

    response, fake_log = _call_structure(handler)

    assert response.data["Reports"] == []
    assert response.data["Files"] == []
    assert client.reports.discovery_calls == 0
    assert client.files.list_calls == 0
    info_messages = [str(call.args[0]) for call in fake_log.info.call_args_list]
    assert not any("远端 IED 未配置报告控制块" in message for message in info_messages)
    assert not any("Files: 返回" in message for message in info_messages)


def test_structure_query_probes_remote_services_after_client_connects():
    handler = IEC61850ClientHandler()
    client = _FakeClient(connected=True)
    handler._client = client
    handler._is_running = True

    response, fake_log = _call_structure(handler)

    assert response.data["Reports"] == []
    assert response.data["Files"] == []
    assert client.reports.discovery_calls == 1
    assert client.files.list_calls == 1
    info_messages = [str(call.args[0]) for call in fake_log.info.call_args_list]
    assert any("远端 IED 未配置报告控制块" in message for message in info_messages)
    assert any("Files: 返回 0" in message for message in info_messages)
