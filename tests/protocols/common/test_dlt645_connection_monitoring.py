import asyncio
import socket

from src.device.core.connection import connection_registry
from src.device.protocol.dlt645_handler import DLT645ServerHandler
from src.enums.modbus_def import ProtocolType


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_dlt645_32_tcp_lifecycle_callbacks_feed_shared_registry():
    async def scenario():
        channel_id = 1645
        closed = []
        connection_registry.set_event_sink(
            lambda event, snapshot: closed.append(snapshot) if event == "closed" else None
        )
        handler = DLT645ServerHandler()
        port = _free_port()
        handler.initialize(
            {
                "channel_id": channel_id,
                "protocol_type": ProtocolType.Dlt645Server,
                "ip": "127.0.0.1",
                "port": port,
                "serial_port": None,
                "meter_address": "000000000001",
                "runtime": {"session_idle_timeout_ms": 30000},
            }
        )
        try:
            assert await handler.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            for _ in range(50):
                current = handler.get_current_connections()
                if current:
                    break
                await asyncio.sleep(0.01)
            assert current[0]["remote_ip"] == "127.0.0.1"
            writer.close()
            await writer.wait_closed()
            for _ in range(50):
                if not handler.get_current_connections():
                    break
                await asyncio.sleep(0.01)
            assert reader.at_eof()
            assert handler.get_current_connections() == []
            assert closed[-1].disconnect_reason.value == "remote_closed"
        finally:
            await handler.stop()
            connection_registry.set_event_sink(None)

    asyncio.run(scenario())
