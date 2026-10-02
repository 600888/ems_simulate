"""Real UA sockets feed the same registry and API used by other protocols."""

import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import Mock

from asyncua import Client, ua
import pytest

from src.data.service.opcua_feature_service import OpcUaFeatureService
from src.data.service.opcua_node_service import OpcUaNodeService
from src.data.service.opcua_security_service import OpcUaSecurityService
from src.device.core.connection import connection_registry
from src.device.protocol.opcua_handler import OpcUaClientHandler, OpcUaServerHandler
from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.connection_observer import ObservedProtocol
from src.proto.opcua.server import OpcUaServer
from src.web.api.device import router
from src.web.api.schemas import ConnectionDetailRequest, DeviceInfoRequest
from tests.protocols.opcua.test_security import identity


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def monitoring(monkeypatch):
    events = []
    monkeypatch.setattr(connection_registry, "_event_sink", lambda event, snapshot: events.append((event, snapshot)))
    monkeypatch.setattr(OpcUaNodeService, "list_nodes", lambda channel_id: [])
    monkeypatch.setattr(OpcUaFeatureService, "load", lambda channel_id: {})
    monkeypatch.setattr(OpcUaSecurityService, "secrets", lambda channel_id: {})
    return events


def handler(channel_id):
    result = OpcUaServerHandler()
    result.initialize(
        {"ip": "127.0.0.1", "port": free_port(), "channel_id": channel_id, "protocol_type": "OpcUaServer"}
    )
    return result


async def wait_for_count(server, expected):
    async with asyncio.timeout(3):
        while server.get_connection_summary()["current_count"] != expected:
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_multiple_clients_api_isolation_reconnect_and_server_stop(monitoring, monkeypatch):
    first, second = handler(9811), handler(9812)
    clients = [Client(first.server.endpoint_url), Client(first.server.endpoint_url), Client(second.server.endpoint_url)]
    try:
        assert first.supports_connection_monitoring()
        assert not hasattr(OpcUaClientHandler(), "supports_connection_monitoring")
        assert await first.start() and await second.start()
        for client in clients:
            await client.connect()
        await clients[0].nodes.server_state.read_value()
        await wait_for_count(first, 2)
        await wait_for_count(second, 1)
        device = SimpleNamespace(
            device_id=9811,
            protocol_handler=first,
            is_protocol_running=lambda: first.is_running,
            ip="127.0.0.1",
            port=first._config["port"],
            protocol_type=SimpleNamespace(value="OpcUaServer"),
            isSimulationRunning=lambda: False,
            iec61850_model_loaded=False,
        )
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(device_controller=SimpleNamespace(device_map={"ua": device})))
        )
        monkeypatch.setattr(router.ChannelDao, "get_all_channels", lambda: [{"id": 9811, "name": "ua"}])
        monkeypatch.setattr(
            router.ConnectionSessionDao,
            "summary_stats",
            lambda channel_id: {
                "history_count": sum(event == "closed" and item.channel_id == channel_id for event, item in monitoring),
                "abnormal_disconnects_today": 0,
            },
        )
        info = await router.get_device_info(DeviceInfoRequest(device_name="ua"), request)
        assert info.data["connection_monitoring_supported"] is True
        assert info.data["current_connection_count"] == 2
        current = await router.get_current_connections(DeviceInfoRequest(device_name="ua"), request)
        assert current.data["supported"] is True
        for item in current.data["items"]:
            assert item["remote_ip"] == item["local_ip"] == "127.0.0.1"
            assert item["remote_port"] > 0 and item["local_port"] == first._config["port"]
            assert item["rx_bytes"] > 0 and item["tx_bytes"] > 0
            assert item["rx_messages"] > 0 and item["tx_messages"] > 0
            assert item["client_identity"]["application_uri"]
            assert item["security"]["mode"] == "None"
        original_ids = {item["session_id"] for item in current.data["items"]}
        detail = await router.get_connection_detail(
            ConnectionDetailRequest(device_name="ua", session_id=current.data["items"][0]["session_id"]), request
        )
        assert detail.data["channel_id"] == 9811
        await clients[0].disconnect()
        await wait_for_count(first, 1)
        closed = [item for event, item in monitoring if event == "closed" and item.channel_id == 9811]
        assert len(closed) == 1 and closed[0].disconnect_reason == "remote_closed"
        await clients[0].connect()
        await wait_for_count(first, 2)
        assert {item["session_id"] for item in first.get_current_connections()} - original_ids
        summary = await router.get_connection_summary(DeviceInfoRequest(device_name="ua"), request)
        assert summary.data["history_count"] == 1
        await first.stop()
        assert first.get_current_connections() == []
        assert second.get_connection_summary()["current_count"] == 1
        closed = [item for event, item in monitoring if event == "closed" and item.channel_id == 9811]
        assert len(closed) == 3
        assert all(item.disconnect_reason == "server_stopped" for item in closed[1:])
        await first.start()
        assert first.get_connection_summary()["current_count"] == 0
    finally:
        for client in clients:
            await client.disconnect()
        await first.stop()
        await second.stop()


@pytest.mark.asyncio
async def test_encrypted_security_and_authentication_failure(monitoring):
    server = handler(9813)
    server_config, server_secrets, server_fingerprint = identity("urn:ems:monitor:server")
    client_config, client_secrets, client_fingerprint = identity("urn:ems:monitor:client")
    server_config.update(trusted=[client_fingerprint], users=[{"username": "reader", "role": "viewer"}])
    from src.proto.opcua.core.security import password_hash

    server_secrets["user:reader"] = password_hash("correct-password")
    client_config.update(trusted=[server_fingerprint], identity="username", username="reader")
    server.server = OpcUaServer(
        "127.0.0.1",
        server._config["port"],
        "urn:ems:monitor",
        features={"security": server_config},
        credentials=server_secrets,
        connection_observer=server._on_connection_event,
    )
    good = OpcUaClient(
        server.server.endpoint_url,
        features={"security": client_config},
        credentials={**client_secrets, "password": "correct-password"},
    )
    bad = OpcUaClient(
        server.server.endpoint_url,
        features={"security": client_config},
        credentials={**client_secrets, "password": "wrong-password"},
    )
    try:
        assert await server.start()
        with pytest.raises(ua.UaStatusCodeError, match="BadUserAccessDenied"):
            await bad.start()
        await wait_for_count(server, 0)
        rejected = [item for event, item in monitoring if event == "closed" and item.channel_id == 9813]
        assert rejected[-1].disconnect_reason == "authentication_failed"
        assert rejected[-1].error_count > 0
        assert "wrong-password" not in str(rejected[-1].to_dict())
        await good.start()
        item = server.get_current_connections()[0]
        assert item["security"]["encrypted"] is True
        assert item["security"]["mode"] == "SignAndEncrypt"
        assert item["security"]["tls"] is False
        assert item["client_identity"]["username"] == "reader"
        await good.stop()
        await wait_for_count(server, 0)
        closed = [item for event, item in monitoring if event == "closed" and item.channel_id == 9813]
        assert closed[-1].client_identity["username"] == "reader"
    finally:
        await bad.stop()
        await good.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_socket_without_ua_session_disappears_on_disconnect(monitoring):
    server = handler(9814)
    try:
        assert await server.start()
        _, writer = await asyncio.open_connection("127.0.0.1", server._config["port"])
        await wait_for_count(server, 1)
        writer.close()
        await writer.wait_closed()
        await wait_for_count(server, 0)
        assert any(event == "closed" and item.channel_id == 9814 for event, item in monitoring)
    finally:
        await server.stop()


def test_network_reset_has_error_reason():
    observer = Mock()
    protocol = ObservedProtocol(Mock(max_pending_messages_per_connection=100), [], [], [], Mock(), observer=observer)
    protocol.connection_lost(ConnectionResetError())
    assert observer.call_args_list[-1].kwargs == {"reason": "network_reset", "detail": "ConnectionResetError"}


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["idle_timeout", "protocol_error", "max_connections_rejected"])
async def test_rejected_or_idle_socket_is_recorded_and_removed(monitoring, reason):
    server = handler(9815)
    writer = None
    try:
        assert await server.start()
        internal = server.server._core._server.iserver
        if reason == "idle_timeout":
            internal.max_pending_activation_seconds = 0.05
        elif reason == "max_connections_rejected":
            internal.max_connections = 0
        reader, writer = await asyncio.open_connection("127.0.0.1", server._config["port"])
        if reason == "protocol_error":
            # A UA TCP header whose advertised length leaves no message body.
            writer.write(b"HELF\x08\x00\x00\x00")
            await writer.drain()
        async with asyncio.timeout(3):
            assert await reader.read() == b""
        await wait_for_count(server, 0)
        closed = [item for event, item in monitoring if event == "closed" and item.channel_id == 9815]
        assert len(closed) == 1
        assert closed[0].disconnect_reason == reason
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        await server.stop()
