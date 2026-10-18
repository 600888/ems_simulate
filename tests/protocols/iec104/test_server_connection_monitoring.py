import asyncio
from datetime import UTC, datetime, timedelta, timezone
import socket
from types import SimpleNamespace

import c104
import pytest

from src.device.core.connection import connection_registry
from src.device.protocol.iec104_handler import IEC104ServerHandler, _c104_connection_time_utc
from src.enums.modbus_def import ProtocolType
from src.web.api.channel.helpers import configure_builder_network

pytestmark = pytest.mark.skipif(
    not hasattr(c104, "ServerConnection"),
    reason="requires the EMS IEC104 fork with server connection lifecycle support",
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.parametrize(
    "value",
    [
        datetime.fromtimestamp(1_788_663_600),
        datetime(2026, 9, 6, 11, tzinfo=timezone(timedelta(hours=8))),
        datetime(2026, 9, 6, 3, tzinfo=UTC),
    ],
)
def test_connection_timestamp_preserves_instant_in_utc(value):
    normalized = _c104_connection_time_utc(value)
    assert normalized.tzinfo is UTC
    assert normalized.timestamp() == value.timestamp()


def test_missing_connection_timestamp_is_preserved():
    assert _c104_connection_time_utc(None) is None


def test_handler_tracks_real_fork_connection_and_disconnect():
    async def scenario():
        channel_id = 1804
        closed = []
        connection_registry.set_event_sink(
            lambda event, snapshot: closed.append(snapshot) if event == "closed" else None
        )
        handler = IEC104ServerHandler()
        port = _free_port()
        handler.initialize(
            {
                "channel_id": channel_id,
                "protocol_type": ProtocolType.Iec104Server,
                "ip": "127.0.0.1",
                "port": port,
                "slave_id_list": [],
                "runtime": {},
                "security": {},
            }
        )
        try:
            assert await handler.start()
            before_connect = datetime.now(UTC)
            client = await asyncio.open_connection("127.0.0.1", port)
            for _ in range(50):
                current = handler.get_current_connections()
                if current:
                    break
                await asyncio.sleep(0.01)
            assert current[0]["remote_ip"] == "127.0.0.1"
            assert current[0]["remote_port"] is not None
            for field in ("transport_connected_at", "established_at", "last_activity_at"):
                connected_at = datetime.fromisoformat(current[0][field])
                assert connected_at.utcoffset() == timedelta(0)
                assert before_connect <= connected_at <= datetime.now(UTC)
            before_disconnect = datetime.now(UTC)
            client[1].close()
            await client[1].wait_closed()
            for _ in range(50):
                if not handler.get_current_connections():
                    break
                await asyncio.sleep(0.01)
            assert handler.get_current_connections() == []
            assert closed[-1].disconnect_reason.value == "remote_closed"
            disconnected_at = datetime.fromisoformat(closed[-1].to_dict()["disconnected_at"])
            assert disconnected_at.utcoffset() == timedelta(0)
            assert before_disconnect <= disconnected_at <= datetime.now(UTC)
        finally:
            await handler.stop()
            connection_registry.set_event_sink(None)

    asyncio.run(scenario())


def test_same_port_servers_keep_connections_on_their_configured_ip():
    async def scenario():
        port = _free_port()
        handlers = []
        writers = []
        try:
            for channel_id, ip in enumerate(("127.0.0.1", "127.0.0.2"), 1942):
                config = {"channel_id": channel_id, "protocol_type": ProtocolType.Iec104Server}
                builder = SimpleNamespace(setDeviceNetConfig=config.update)
                configure_builder_network(builder, 2, ProtocolType.Iec104Server, ip, port, {})
                handler = IEC104ServerHandler()
                handlers.append(handler)
                handler.initialize(config)
                assert await handler.start(), f"Could not listen on {ip}:{port}"

            for ip in ("127.0.0.1", "127.0.0.2"):
                reader, writer = await asyncio.open_connection(ip, port)
                writers.append(writer)
                writer.write(bytes.fromhex("68 04 07 00 00 00"))  # STARTDT_ACT
                await writer.drain()
                assert await asyncio.wait_for(reader.readexactly(6), 2) == bytes.fromhex("68 04 0b 00 00 00")

            for _ in range(100):
                connections = [handler.get_current_connections() for handler in handlers]
                if all(len(items) == 1 for items in connections):
                    break
                await asyncio.sleep(0.01)
            for index, ip in enumerate(("127.0.0.1", "127.0.0.2")):
                assert len(connections[index]) == 1
                assert connections[index][0]["local_ip"] == ip
                assert connections[index][0]["local_port"] == port
                assert connections[index][0]["channel_id"] == 1942 + index

            await handlers[0].stop()
            assert handlers[0].get_current_connections() == []
            assert len(handlers[1].get_current_connections()) == 1
            # The surviving server must not take over the stopped server's IP.
            try:
                _, unexpected_writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 0.5)
            except (OSError, TimeoutError):
                pass
            else:
                writers.append(unexpected_writer)
                pytest.fail("The surviving server accepted a connection for the stopped server's IP")
            writers[1].write(bytes.fromhex("68 04 43 00 00 00"))  # TESTFR_ACT
            await writers[1].drain()
            assert await asyncio.wait_for(reader.readexactly(6), 2) == bytes.fromhex("68 04 83 00 00 00")
        finally:
            for writer in writers:
                writer.close()
                await writer.wait_closed()
            for handler in handlers:
                await handler.stop()

    asyncio.run(scenario())
