from unittest.mock import Mock

from src.proto.iec104.iec104client import IEC104Client


def _client(*, connected: bool = True, tls_bridge=None) -> IEC104Client:
    client = IEC104Client.__new__(IEC104Client)
    client.ip = "192.0.2.10"
    client.port = 2404
    client.connection = Mock(is_connected=connected)
    client.client = Mock()
    client._tls_bridge = tls_bridge
    return client


def test_disconnect_uses_error_level_and_includes_connection_details(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    client = _client()

    client.disconnect()

    client.connection.disconnect.assert_called_once_with()
    client.client.stop.assert_called_once_with()
    protocol_log.info.assert_not_called()
    protocol_log.error.assert_called_once()
    message = protocol_log.error.call_args.args[0]
    assert "服务器=192.0.2.10:2404" in message
    assert "传输方式=TCP" in message
    assert "断开前状态=已连接" in message
    assert "IEC104连接=已断开" in message
    assert "IEC104客户端=已停止" in message
    assert "TLS桥接器=未启用" in message


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
    assert "传输方式=TLS" in message
    assert "IEC104连接断开失败(ConnectionError: peer reset)" in message
    assert "TLS桥接器停止失败(OSError: TLS socket closed unexpectedly)" in message
