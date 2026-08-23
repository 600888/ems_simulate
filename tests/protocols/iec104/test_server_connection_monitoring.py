import asyncio
import socket

import c104
import pytest

from src.device.core.connection import connection_registry
from src.device.protocol.iec104_handler import IEC104ServerHandler
from src.enums.modbus_def import ProtocolType

pytestmark = pytest.mark.skipif(
    not hasattr(c104, "ServerConnection"),
    reason="requires the EMS IEC104 fork with server connection lifecycle support",
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


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
            client = await asyncio.open_connection("127.0.0.1", port)
            for _ in range(50):
                current = handler.get_current_connections()
                if current:
                    break
                await asyncio.sleep(0.01)
            assert current[0]["remote_ip"] == "127.0.0.1"
            assert current[0]["remote_port"] is not None
            client[1].close()
            await client[1].wait_closed()
            for _ in range(50):
                if not handler.get_current_connections():
                    break
                await asyncio.sleep(0.01)
            assert handler.get_current_connections() == []
            assert closed[-1].disconnect_reason.value == "remote_closed"
        finally:
            await handler.stop()
            connection_registry.set_event_sink(None)

    asyncio.run(scenario())
