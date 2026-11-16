import asyncio
from unittest.mock import Mock

import c104

from src.proto.iec104.iec104client import IEC104Client


def _client(*, connected: bool = True, tls_bridge=None) -> IEC104Client:
    client = IEC104Client.__new__(IEC104Client)
    client.ip = "192.0.2.10"
    client.port = 2404
    client.connection = Mock(is_connected=connected, is_muted=False)
    client.client = Mock()
    client._tls_bridge = tls_bridge
    client._disconnect_requested = False
    client._ever_connected = connected
    client._connect_in_progress = False
    client._connection_active = connected
    client._connect_failed = False
    client._saw_tcp_open = False
    client._connect_lock = asyncio.Lock()
    client._loop = None
    client._transport_stop_task = None
    client.last_error = ""
    return client


def test_disconnect_uses_info_level_and_includes_connection_details(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client()

    client.disconnect()

    client.connection.disconnect.assert_called_once_with()
    client.client.stop.assert_called_once_with()
    protocol_log.error.assert_not_called()
    protocol_log.info.assert_called_once()
    message = protocol_log.info.call_args.args[0]
    assert "服务器：192.0.2.10:2404" in message
    assert "传输方式：TCP" in message
    assert "断开前状态：已连接" in message
    assert "IEC104连接：已断开" in message
    assert "IEC104客户端：已停止" in message
    assert "TLS桥接器：未启用" in message
    assert client._disconnect_requested is True


def test_disconnect_reports_each_cleanup_error_and_continues_cleanup(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    tls_bridge = Mock()
    tls_bridge.stop.side_effect = OSError("TLS socket closed unexpectedly")
    client = _client(tls_bridge=tls_bridge)
    client.connection.disconnect.side_effect = ConnectionError("peer reset")

    client.disconnect()

    client.connection.disconnect.assert_called_once_with()
    client.client.stop.assert_called_once_with()
    tls_bridge.stop.assert_called_once_with()
    protocol_log.error.assert_called_once()
    message = protocol_log.error.call_args.args[0]
    assert "传输方式：TLS" in message
    assert "IEC104连接断开失败(ConnectionError: peer reset)" in message
    assert "TLS桥接器停止失败(OSError: TLS socket closed unexpectedly)" in message


def test_state_change_distinguishes_unexpected_and_requested_disconnect(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client(connected=False)

    client._on_state_change(client.connection, c104.ConnectionState.OPEN)
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_OPEN)
    protocol_log.error.assert_not_called()
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_RECONNECT)
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_OPEN)
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_RECONNECT)

    protocol_log.error.assert_called_once()
    assert "非预期断开" in protocol_log.error.call_args.args[0]

    protocol_log.reset_mock()
    client._disconnect_requested = True
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED)

    protocol_log.error.assert_not_called()
    protocol_log.info.assert_not_called()


def test_muted_tcp_connection_is_not_ready_and_does_not_report_an_established_session_loss(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client(connected=False)
    client.connection.is_connected = True
    client.connection.is_muted = True

    client._on_state_change(client.connection, c104.ConnectionState.OPEN_MUTED)
    assert client.is_connected is False
    assert client._ever_connected is False
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_RECONNECT)
    protocol_log.error.assert_not_called()
    protocol_log.info.assert_not_called()


def test_late_open_callback_cannot_undo_explicit_disconnect(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client(connected=False)
    client._disconnect_requested = True
    client._on_state_change(client.connection, c104.ConnectionState.OPEN_MUTED)
    client._on_state_change(client.connection, c104.ConnectionState.OPEN)
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_RECONNECT)
    assert client._disconnect_requested is True
    assert client._connection_active is False
    protocol_log.error.assert_not_called()


def test_connect_fails_once_when_peer_closes_before_startdt(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client(connected=False)

    def fail_handshake():
        client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_OPEN)
        client._on_state_change(client.connection, c104.ConnectionState.OPEN_MUTED)
        client.connection.state = c104.ConnectionState.CLOSED_AWAIT_RECONNECT
        client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_RECONNECT)

    client.client.start.side_effect = fail_handshake
    assert asyncio.run(client.connect(timeout=10)) is False
    client.client.stop.assert_called_once_with()
    assert "STARTDT" in client.last_error
    assert "192.0.2.10:2404" in client.last_error
    protocol_log.error.assert_called_once()
    protocol_log.info.assert_not_called()


def test_concurrent_connect_requests_share_one_native_start(monkeypatch):
    monkeypatch.setattr("src.proto.iec104.iec104client.log", Mock())
    client = _client(connected=False)

    def connected():
        client.connection.is_connected = True
        client._on_state_change(client.connection, c104.ConnectionState.OPEN)

    client.client.start.side_effect = connected

    async def scenario():
        return await asyncio.gather(*(client.connect() for _ in range(5)))

    assert asyncio.run(scenario()) == [True] * 5
    client.client.start.assert_called_once_with()


def test_connection_loss_stops_native_retry_scheduler_without_blocking_callback(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client()

    async def scenario():
        client._loop = asyncio.get_running_loop()
        client.connection.is_connected = False
        client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_RECONNECT)
        # Let the thread-safe callback create the cleanup coroutine.
        await asyncio.sleep(0)
        assert client._transport_stop_task is not None
        await client._transport_stop_task

    asyncio.run(scenario())
    client.client.stop.assert_called_once_with()
    protocol_log.error.assert_called_once()
    assert client._disconnect_requested is True
