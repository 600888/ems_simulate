from types import SimpleNamespace
from unittest.mock import Mock

from pydantic import ValidationError as PydanticValidationError
import pytest

from src.device.protocol.base_handler import ServerHandler
from src.web.api.device import router
from src.web.api.schemas import ConnectionHistoryClearRequest, ConnectionHistoryRequest, DeviceInfoRequest


class _MonitoredServerHandler(ServerHandler):
    def initialize(self, config):
        self._configure_connection_monitoring(config, supported=True)

    async def start(self):
        self._is_running = True
        return True

    async def stop(self):
        self._is_running = False
        self._close_all_connections()
        return True

    def read_value(self, point):
        return None

    def write_value(self, point, value):
        return True

    def add_points(self, points):
        return None

    def clear_captured_messages(self):
        return None

    def get_value_by_address(self, func_code, slave_id, address):
        return None

    def set_value_by_address(self, func_code, slave_id, address, value):
        return None


def _request(device):
    controller = SimpleNamespace(device_map={"server": device})
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))


@pytest.mark.asyncio
async def test_current_and_summary_use_live_registry(monkeypatch):
    handler = _MonitoredServerHandler()
    handler.initialize({"channel_id": 42, "protocol_type": "ModbusTcpServer"})
    handler._is_running = True
    event_sink = router.connection_registry._event_sink
    router.connection_registry.set_event_sink(None)
    handler._open_connection("client-1", remote_endpoint=("2001:db8::1", 41000))
    device = SimpleNamespace(device_id=42, protocol_handler=handler, is_protocol_running=Mock(return_value=True))
    monkeypatch.setattr(
        router.ConnectionSessionDao,
        "summary_stats",
        lambda _channel_id: {"history_count": 7, "abnormal_disconnects_today": 2},
    )

    try:
        current = await router.get_current_connections(DeviceInfoRequest(device_name="server"), _request(device))
        summary = await router.get_connection_summary(DeviceInfoRequest(device_name="server"), _request(device))

        assert current.data["supported"] is True
        assert current.data["items"][0]["remote_ip"] == "2001:db8::1"
        assert summary.data["server_running"] is True
        assert summary.data["current_count"] == 1
        assert summary.data["history_count"] == 7
    finally:
        handler._close_all_connections()
        router.connection_registry.set_event_sink(event_sink)


@pytest.mark.asyncio
async def test_unsupported_mode_returns_empty_without_fake_connections():
    device = SimpleNamespace(
        device_id=43,
        protocol_handler=object(),
        is_protocol_running=Mock(return_value=True),
    )

    response = await router.get_current_connections(DeviceInfoRequest(device_name="server"), _request(device))

    assert response.data == {
        "supported": False,
        "unsupported_reason": "not_a_supported_network_server",
        "items": [],
    }


@pytest.mark.asyncio
async def test_clear_history_scopes_to_requested_device_without_closing_connections(monkeypatch):
    handler = _MonitoredServerHandler()
    handler.initialize({"channel_id": 44, "protocol_type": "ModbusTcpServer"})
    event_sink = router.connection_registry._event_sink
    router.connection_registry.set_event_sink(None)
    handler._open_connection("live", remote_endpoint=("192.0.2.1", 41000))
    device = SimpleNamespace(device_id=44, protocol_handler=handler)
    clear = Mock(return_value=7)
    monkeypatch.setattr(router.connection_persistence, "clear_history", clear)
    try:
        response = await router.clear_connection_history(
            ConnectionHistoryClearRequest(device_name="server"), _request(device)
        )
        assert response.data == {"deleted_count": 7}
        clear.assert_called_once_with(44)
        assert len(handler.get_current_connections()) == 1
    finally:
        handler._close_all_connections()
        router.connection_registry.set_event_sink(event_sink)


@pytest.mark.asyncio
async def test_clear_history_rejects_unsupported_device(monkeypatch):
    clear = Mock()
    monkeypatch.setattr(router.connection_persistence, "clear_history", clear)
    device = SimpleNamespace(device_id=43, protocol_handler=object())
    with pytest.raises(router.ValidationError):
        await router.clear_connection_history(ConnectionHistoryClearRequest(device_name="server"), _request(device))
    clear.assert_not_called()


@pytest.mark.asyncio
async def test_clear_history_by_channel_id_works_without_runtime_device(monkeypatch):
    lookup = Mock(return_value={"id": 71, "name": "Stopped server", "device_id": 900})
    clear = Mock(return_value=4)
    monkeypatch.setattr(router.ChannelDao, "get_channel_by_id", lookup)
    monkeypatch.setattr(router.connection_persistence, "clear_history", clear)
    response = await router.clear_connection_history(ConnectionHistoryClearRequest(channel_id=71), SimpleNamespace())
    assert response.data == {"deleted_count": 4}
    lookup.assert_called_once_with(71)
    clear.assert_called_once_with(71)


@pytest.mark.asyncio
async def test_clear_history_by_missing_channel_does_not_delete(monkeypatch):
    monkeypatch.setattr(router.ChannelDao, "get_channel_by_id", Mock(return_value=None))
    clear = Mock()
    monkeypatch.setattr(router.connection_persistence, "clear_history", clear)
    with pytest.raises(router.NotFoundError):
        await router.clear_connection_history(ConnectionHistoryClearRequest(channel_id=71), SimpleNamespace())
    clear.assert_not_called()


@pytest.mark.parametrize("values", [{}, {"channel_id": 0}, {"channel_id": 1, "device_name": "server"}])
def test_clear_history_requires_one_explicit_device(values):
    with pytest.raises(PydanticValidationError):
        ConnectionHistoryClearRequest(**values)


def test_history_request_validates_page_size_and_ip_address():
    assert ConnectionHistoryRequest(device_name="server", remote_ip="2001:db8::8").remote_ip == "2001:db8::8"
    with pytest.raises(PydanticValidationError):
        ConnectionHistoryRequest(device_name="server", page_size=101)
    with pytest.raises(PydanticValidationError):
        ConnectionHistoryRequest(device_name="server", remote_ip="not-an-ip")
