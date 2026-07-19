from unittest.mock import Mock

import c104

from src.proto.iec104.iec104client import IEC104Client


def _client(*, connected: bool = True, tls_bridge=None) -> IEC104Client:
    client = IEC104Client.__new__(IEC104Client)
    client.ip = "192.0.2.10"
    client.port = 2404
    client.connection = Mock(is_connected=connected)
    client.client = Mock()
    client._tls_bridge = tls_bridge
    client._disconnect_requested = False
    client._ever_connected = connected
    client._connect_in_progress = False
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

    client._on_state_change(client.connection, c104.ConnectionState.OPEN_MUTED)
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED_AWAIT_OPEN)

    protocol_log.error.assert_called_once()
    assert "非预期断开" in protocol_log.error.call_args.args[0]

    protocol_log.reset_mock()
    client._disconnect_requested = True
    client._on_state_change(client.connection, c104.ConnectionState.CLOSED)

    protocol_log.error.assert_not_called()
    protocol_log.info.assert_called_once()
